#!/bin/bash

# kill other instances of this script
pgrep "$(basename $0)" | grep -v "$$" | xargs --no-run-if-empty kill 


test_string="(pgrep $(basename $0) | grep --line-regexp $$)"
test_string="\$$test_string"

start=$(date +%s)
duration=$((${1:-50} * 60))
current='$(date +%s)'
echo_string="((($start + $duration - $current) / 60)) min | iconName=system-lock-screen"
echo_string="\$$echo_string"

cat <<EOF > $HOME/.config/argos/auto-lock-indicator.1s.sh
#!/usr/bin/env bash

if [[ "$test_string" ]]
then
    echo "$echo_string"
else
    echo " "
fi
EOF

echo "Sleep $duration seconds"
sleep $duration
for i in {1..240}
    do
        echo "Locking"
        xdg-screensaver lock
        sleep 1
    done


