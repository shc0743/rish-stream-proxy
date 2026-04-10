#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/select.h>
#include <fcntl.h>
#include <cerrno>
#include <string>
#include <vector>

// 协议格式：
// [uint8_t type][uint64_t length][data...]
// type: 1=stdout, 2=stderr, 3=exitcode
// length: 小端序

static void write_packet(uint8_t type, const void* data, uint64_t len) {
    // 写入类型
    if (write(STDOUT_FILENO, &type, 1) != 1) {
        _exit(1);
    }
    
    // 写入长度（小端序）
    uint64_t len_le = len;
    // 简单实现：按字节写入
    for (int i = 0; i < 8; i++) {
        uint8_t b = (len_le >> (i * 8)) & 0xFF;
        if (write(STDOUT_FILENO, &b, 1) != 1) {
            _exit(1);
        }
    }
    
    // 写入数据
    if (len > 0) {
        const uint8_t* bytes = static_cast<const uint8_t*>(data);
        uint64_t written = 0;
        while (written < len) {
            ssize_t n = write(STDOUT_FILENO, bytes + written, len - written);
            if (n <= 0) {
                _exit(1);
            }
            written += n;
        }
    }
}

static void set_nonblock(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags >= 0) {
        fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    }
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <command> [args...]\n", argv[0]);
        return 1;
    }
    
    // 创建管道用于 stdout
    int stdout_pipe[2];
    if (pipe(stdout_pipe) == -1) {
        perror("pipe stdout");
        return 1;
    }
    
    // 创建管道用于 stderr
    int stderr_pipe[2];
    if (pipe(stderr_pipe) == -1) {
        perror("pipe stderr");
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        return 1;
    }
    
    pid_t pid = fork();
    if (pid == -1) {
        perror("fork");
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        close(stderr_pipe[0]);
        close(stderr_pipe[1]);
        return 1;
    }
    
    if (pid == 0) { // 子进程
        // 关闭不需要的管道端
        close(stdout_pipe[0]);
        close(stderr_pipe[0]);
        
        // 重定向 stdout 到管道
        if (dup2(stdout_pipe[1], STDOUT_FILENO) == -1) {
            perror("dup2 stdout");
            _exit(1);
        }
        close(stdout_pipe[1]);
        
        // 重定向 stderr 到管道
        if (dup2(stderr_pipe[1], STDERR_FILENO) == -1) {
            perror("dup2 stderr");
            _exit(1);
        }
        close(stderr_pipe[1]);
        
        // 执行命令
        execvp(argv[1], argv + 1);
        perror("execvp");
        _exit(127);
    }
    
    // 父进程
    close(stdout_pipe[1]);
    close(stderr_pipe[1]);
    
    // 设置非阻塞
    set_nonblock(stdout_pipe[0]);
    set_nonblock(stderr_pipe[0]);
    
    fd_set readfds;
    int max_fd = (stdout_pipe[0] > stderr_pipe[0]) ? stdout_pipe[0] : stderr_pipe[0];
    max_fd = (max_fd > STDIN_FILENO) ? max_fd : STDIN_FILENO;
    
    std::vector<uint8_t> buffer(4096);
    bool stdout_eof = false;
    bool stderr_eof = false;
    
    while (!stdout_eof || !stderr_eof) {
        FD_ZERO(&readfds);
        if (!stdout_eof) {
            FD_SET(stdout_pipe[0], &readfds);
        }
        if (!stderr_eof) {
            FD_SET(stderr_pipe[0], &readfds);
        }
        
        int ret = select(max_fd + 1, &readfds, nullptr, nullptr, nullptr);
        if (ret == -1) {
            if (errno == EINTR) continue;
            perror("select");
            break;
        }
        
        // 读取 stdout
        if (!stdout_eof && FD_ISSET(stdout_pipe[0], &readfds)) {
            ssize_t n = read(stdout_pipe[0], buffer.data(), buffer.size());
            if (n > 0) {
                write_packet(1, buffer.data(), n);
            } else if (n == 0) {
                stdout_eof = true;
                close(stdout_pipe[0]);
            } else {
                if (errno != EAGAIN && errno != EWOULDBLOCK) {
                    perror("read stdout");
                    break;
                }
            }
        }
        
        // 读取 stderr
        if (!stderr_eof && FD_ISSET(stderr_pipe[0], &readfds)) {
            ssize_t n = read(stderr_pipe[0], buffer.data(), buffer.size());
            if (n > 0) {
                write_packet(2, buffer.data(), n);
            } else if (n == 0) {
                stderr_eof = true;
                close(stderr_pipe[0]);
            } else {
                if (errno != EAGAIN && errno != EWOULDBLOCK) {
                    perror("read stderr");
                    break;
                }
            }
        }
    }
    
    // 等待子进程结束
    int status;
    waitpid(pid, &status, 0);
    
    if (WIFEXITED(status)) {
        uint8_t exit_code = WEXITSTATUS(status);
        write_packet(3, &exit_code, 1);
        return exit_code;
    } else if (WIFSIGNALED(status)) {
        uint8_t sig = WTERMSIG(status);
        write_packet(4, &sig, 1);
        return 128 + sig;
    } else {
        return 1;
    }
}
