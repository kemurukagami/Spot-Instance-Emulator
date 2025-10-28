#!/bin/bash
set -e

# Set root password from environment variable
if [ -n "$ROOT_PASSWORD" ]; then
    echo "root:$ROOT_PASSWORD" | chpasswd
    echo "Root password set from environment"
else
    echo "root:defaultpassword" | chpasswd
    echo "WARNING: Using default password"
fi

# Start SSH service
echo "Starting SSH server..."
/usr/sbin/sshd -D
