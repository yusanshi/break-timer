#!/bin/bash

# kill other instances of this script
pgrep "$(basename $0)" | grep -v "$$" | xargs --no-run-if-empty kill 

INDICATOR_TARGET=$HOME/.config/argos/auto-lock-indicator.1s.sh

while true
do
    duration=$((${1:-50} * 60))
    echo "Sleep $duration seconds"

    start=$(date +%s)
    remained_string='$(($start+$duration-$(date +%s)))'

    cat <<EOF > $INDICATOR_TARGET
#!/usr/bin/env bash

start=$start
duration=$duration

echo "$remained_string seconds | iconName=system-lock-screen"
EOF

    sleep $duration
    for i in {1..200}
        do
            echo "Locking"
            xdg-screensaver lock
            sleep 1
        done
done

