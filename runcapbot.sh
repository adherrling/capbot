#!/bin/bash
echo "Running..."
pkill -F /home/austin/Documents/capbot/pid.pid
/usr/bin/python3.6 /home/austin/Documents/capbot/capbot.py -c &
echo $! > /home/austin/Documents/capbot/pid.pid
