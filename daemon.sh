#!/bin/bash

echo "[$(date)] logged in, running the script..." >> $HOME/auto-lock/log.txt
$HOME/auto-lock/auto-lock.sh &

dbus-monitor --session "type='signal',interface='org.gnome.ScreenSaver'" |
  while read x
  do
    case "$x" in
      *"boolean true"*)
        echo "[$(date)] locked. " >> $HOME/auto-lock/log.txt
        ;;
      *"boolean false"*)
        echo "[$(date)] unlocked, running the script..." >> $HOME/auto-lock/log.txt
        $HOME/auto-lock/auto-lock.sh &
        ;;
    esac
  done
