#!/bin/bash

echo "[$(date)] startup, running the script..." >> $HOME/auto-lock/log.txt
$HOME/auto-lock/auto-lock.sh &

dbus-monitor --session "type='signal',interface='org.gnome.ScreenSaver'" | \
( while true
    do read X
    if echo $X | grep "boolean true" &> /dev/null; then
        echo "[$(date)] locked. " >> $HOME/auto-lock/log.txt
    elif echo $X | grep "boolean false" &> /dev/null; then
        echo "[$(date)] unlocked, running the script..." >> $HOME/auto-lock/log.txt
        $HOME/auto-lock/auto-lock.sh &
    fi
    done )
