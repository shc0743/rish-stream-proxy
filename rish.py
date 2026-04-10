#!/usr/bin/env python3
"""
Final Rish Client with proper stdout/stderr separation
Key insight: rish randomly mixes stdout and stderr, so we must redirect 
rish's stderr to stdout (2>&1) and parse the combined stream.
"""

import sys
import os
import subprocess
import struct
import argparse
import shutil
import threading
import time

RISH_PATH = os.path.expanduser("~/rish")
REMOTE_PROXY_PATH = "/data/user_de/0/com.android.shell/files/rish_stream_proxy"
SDCARD_PATH = "/sdcard/rish_stream_proxy"

def parse_args():
    parser = argparse.ArgumentParser(description="Rish client with proper stdout/stderr handling")
    parser.add_argument("-c", "--command", help="Command to execute")
    parser.add_argument("--copy", metavar="PATH", help="Copy local proxy binary to remote")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    return parser.parse_args()

def copy_proxy_to_remote(local_path):
    """Copy proxy binary to remote shell directory"""
    print(f"Copying proxy binary to remote...", file=sys.stderr)
    
    try:
        shutil.copy2(local_path, SDCARD_PATH)
        os.chmod(SDCARD_PATH, 0o755)
    except Exception as e:
        print(f"Failed to copy to sdcard: {e}", file=sys.stderr)
        return False
    
    cmd = f'cp "{SDCARD_PATH}" "{REMOTE_PROXY_PATH}" && chmod 755 "{REMOTE_PROXY_PATH}"'
    result = subprocess.run([RISH_PATH, "-c", cmd], 
                          capture_output=True, text=True, timeout=10)
    
    if result.returncode != 0:
        print(f"Failed to copy to remote: {result.stderr}", file=sys.stderr)
        return False
    
    print("Proxy binary copied successfully", file=sys.stderr)
    return True

def read_exactly(fd, n, timeout=5):
    """Read exactly n bytes from file descriptor with timeout"""
    data = b""
    start_time = time.time()
    
    while len(data) < n:
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Timeout reading {n} bytes, got {len(data)}")
        
        try:
            # Use select to check if data is available
            import select
            rlist, _, _ = select.select([fd], [], [], 0.1)
            if fd in rlist:
                chunk = os.read(fd, n - len(data))
                if not chunk:  # EOF
                    break
                data += chunk
            elif time.time() - start_time > timeout:
                raise TimeoutError(f"Timeout reading {n} bytes")
        except (OSError, ValueError) as e:
            if "bad file descriptor" in str(e):
                break
            raise
    
    return data

def run_command(command, debug=False):
    """Execute command through rish_stream_proxy"""
    # Build the remote command
    remote_cmd = f'"{REMOTE_PROXY_PATH}" sh -c {repr(command)}'
    
    if debug:
        print(f"Remote command: {remote_cmd}", file=sys.stderr)
    
    # Run rish with stderr redirected to stdout (2>&1)
    # This is CRITICAL because rish randomly mixes stdout and stderr
    proc = subprocess.Popen(
        [RISH_PATH, "-c", remote_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Redirect stderr to stdout
        stdin=subprocess.DEVNULL,
        bufsize=0
    )
    
    combined_fd = proc.stdout.fileno()
    exit_code = None
    
    try:
        while True:
            # Read packet type (1 byte)
            type_bytes = read_exactly(combined_fd, 1, timeout=2)
            if not type_bytes:
                break
                
            packet_type = type_bytes[0]
            
            # Read length (8 bytes, little-endian)
            length_bytes = read_exactly(combined_fd, 8, timeout=2)
            if len(length_bytes) != 8:
                break
                
            length = struct.unpack("<Q", length_bytes)[0]
            
            if debug and length > 1000000:
                print(f"Warning: Large packet length {length}", file=sys.stderr)
            
            # Read data
            data = b""
            if length > 0:
                data = read_exactly(combined_fd, length, timeout=5)
                if len(data) != length:
                    if debug:
                        print(f"Incomplete data: expected {length}, got {len(data)}", file=sys.stderr)
                    break
            
            # Process packet
            if packet_type == 1:  # stdout
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            elif packet_type == 2:  # stderr
                sys.stderr.buffer.write(data)
                sys.stderr.buffer.flush()
            elif packet_type == 3:  # exitcode
                if data:
                    exit_code = data[0] if len(data) >= 1 else 0
                    if debug:
                        print(f"\n[Exit code: {exit_code}]", file=sys.stderr)
            elif packet_type == 4:  # signal
                if data:
                    sig = data[0] if len(data) >= 1 else 0
                    if debug:
                        print(f"\n[Signal: {sig}]", file=sys.stderr)
                    exit_code = 128 + sig
            else:
                if debug:
                    print(f"\n[Unknown packet type: {packet_type}]", file=sys.stderr)
                # Try to continue anyway
    
    except (OSError, EOFError, TimeoutError) as e:
        if debug:
            print(f"\n[Stream error: {e}]", file=sys.stderr)
    
    # Wait for process
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if debug:
            print("[Process timeout, terminating]", file=sys.stderr)
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    
    if exit_code is None:
        exit_code = proc.returncode
    
    return exit_code

def main():
    args = parse_args()
    
    if args.copy:
        if not os.path.exists(args.copy):
            print(f"Error: Proxy binary not found at {args.copy}", file=sys.stderr)
            sys.exit(1)
        if not copy_proxy_to_remote(args.copy):
            sys.exit(1)
        return 0
    
    # Quick check if proxy exists
    if args.debug:
        check_cmd = f'[ -x "{REMOTE_PROXY_PATH}" ] && echo "exists" || echo "missing"'
        result = subprocess.run([RISH_PATH, "-c", check_cmd], 
                              capture_output=True, text=True)
        print(f"Proxy check: {result.stdout.strip()}", file=sys.stderr)
        if "missing" in result.stdout:
            print("Warning: Proxy binary not found on remote side!", file=sys.stderr)
            print(f"Run: {sys.argv[0]} --copy ~/rish_stream_proxy", file=sys.stderr)
            
    if not args.command:
        exit_code = subprocess.call(["rish"] + sys.argv[1:])
    else:
        exit_code = run_command(args.command, args.debug)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
