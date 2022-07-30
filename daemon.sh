#!/bin/bash

target_file=$HOME/auto-lock/auto-lock.sh
log_file=$HOME/auto-lock/log.txt

echo "[$(date)] logged in, running the script..." | tee -a $log_file
$target_file &

history_unlocked=$(gnome-screensaver-command -q | grep "is inactive")
while true
do
  sleep 1
  current_unlocked=$(gnome-screensaver-command -q | grep "is inactive")
  if [[ ! $history_unlocked ]] && [[ $current_unlocked ]]
  then
    echo "[$(date)] unlocked, running the script..." | tee -a $log_file
    $target_file &
  fi
  if [[ $history_unlocked ]] && [[ ! $current_unlocked ]]
  then
    echo "[$(date)] locked. " | tee -a $log_file
  fi
  history_unlocked=$current_unlocked
done
