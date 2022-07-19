#!/bin/bash

# kill other instances of this script
pgrep "$(basename $0)" | grep -v "$$" | xargs --no-run-if-empty kill 

while true
do
    interval=$((${1:-50} * 60))
    echo "Sleep $interval seconds"
    sleep $interval
    for i in {1..200}
        do
            echo "Locking"
            xdg-screensaver lock
            sleep 1
        done
done

