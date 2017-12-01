#!/bin/bash
echo "Running..."
pkill -F /home/austin/Documents/capbot/pid.pid
/usr/bin/python3.6 -u /home/austin/Documents/capbot/capbot.py -c >> /home/austin/Documents/capbot/log.log 2>&1 &
echo $! > /home/austin/Documents/capbot/pid.pid
