#!/bin/bash

echo "[$(date)] logged in, running the script..." >> $HOME/auto-lock/log.txt
$HOME/auto-lock/auto-lock.sh &

gdbus monitor -y -d org.freedesktop.login1 |
  while read x
  do
    case "$x" in
      *"{'LockedHint': <true>}"*)
        echo "[$(date)] locked. " >> $HOME/auto-lock/log.txt
        ;;
      *"{'LockedHint': <false>}"*)
        echo "[$(date)] unlocked, running the script..." >> $HOME/auto-lock/log.txt
        $HOME/auto-lock/auto-lock.sh &
        ;;
    esac
  done
