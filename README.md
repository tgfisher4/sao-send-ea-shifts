# sao-send-ea-shifts
This repository holds a python script which grabs data from the Notre Dame Student Activities Office Event Assistant Request spreadsheet (Google Sheets) and prints a message that can be sent out requesting the appropriate number of Event Assistants for the appropriate shifts for a given day.

This is a small personal project to automate a responsibility I have found tedious entailed by one of my student jobs. I work on it when I have some free time.
Recently, the format of the spreadsheet has changed and I have not had time to update this script yet. If you run this script with the `-t` flag, however, it will access a test spreadsheet I set up which is in the currently expected format (which does not match the format of the live spreadsheet). I designed this script with the goal to apply functional programming techniques I learned about over the summer.

The next steps are to connect to the GroupMe API to automate the sending of the message it prints to `stdout`.
