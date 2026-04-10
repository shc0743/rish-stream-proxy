# Rish Stdout/Stderr Fix

## The Problem
Rish (Shizuku remote shell) has a critical bug that randomly mixes stdout and stderr output,
making it impossible to use with pipes, redirections, or any batch processing.

**Bug details:**
- Issue #178: "[not braindead issue] rish mixes up stdout and stderr" (open since Jan 2025)
- Issue #368: "rish stdout/stderr random mixing bug..." (open since Feb 2026)
- Root cause: In `RishTerminal.java` line 77, `getFd(stdout, 0)` is passed twice instead of `getFd(stderr, 0)`

## Solution
This project provides a complete workaround that:
1. Uses a custom binary protocol to properly separate stdout and stderr
2. Works around rish's bug by redirecting rish's stderr to stdout and parsing the combined stream
3. Provides a drop-in replacement for rish commands

## Files
- `rish_stream_proxy`: C++ binary that runs commands and outputs protocol packets
- `rish.py`: Python client that communicates with the proxy (formerly named `rish_client_final.py`)
- `rish_stream_proxy.cpp`: Source code for the proxy
- `install.sh`: Installation script to compile and deploy the proxy

## Installation

### Automatic installation
```bash
cd ~/rish-fix
./install.sh
```

### Manual installation
1. **Compile the proxy** (if needed):
   ```bash
   cd ~/rish-fix
   clang++ -std=c++17 -o rish_stream_proxy rish_stream_proxy.cpp
   ```
   If you don't have clang++, you can use the pre‑compiled binary (if available).

2. **Copy the proxy to the remote shell** (requires Shizuku running):
   ```bash
   ./rish.py --copy ./rish_stream_proxy
   ```

3. **Make scripts executable** (if needed):
   ```bash
   chmod +x rish.py rish_stream_proxy
   ```

## Usage

Replace `rish -c "command"` with:
```bash
~/rish-fix/rish.py -c "command"
```

Or create an alias:
```bash
alias rish-fixed='~/rish-fix/rish.py'
rish-fixed -c "your command"
```

### Testing the fix
```bash
# Basic test
./rish.py -c 'echo stdout; echo stderr >&2'

# With redirections
./rish.py -c 'ls /nonexistent 2>&1'

# Complex pipelines
./rish.py -c 'ls -F /proc/self/fd 2>&1 | head -5'
```

## How It Works

### Protocol Format
```
[uint8_t type][uint64_t length_le][data...]
```
- Type 1: stdout data
- Type 2: stderr data  
- Type 3: exit code (1 byte)
- Type 4: signal (1 byte)

### Architecture
```
Your Terminal
     |
[rish.py] --(parses protocol)--> separates stdout/stderr
     |
  [rish] --(buggy, mixed output)-->
     |
[rish_stream_proxy] --(clean protocol packets)-->
     |
  [sh -c "your command"] --(proper stdout/stderr)-->
```

### Critical Insight
Rish randomly sends output to either stdout or stderr, so we must run rish with `2>&1` and parse the combined stream.

## Performance
Slightly slower than native rish due to protocol overhead, but reliable.

## License
MIT
