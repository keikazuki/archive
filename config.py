# -*- coding: utf-8 -*-

'''
List of All Configurations
'''

#Reddit configuration for DoujinStash
USERNAME        = 'kei-kazuki'
PASSWORD        = 'beyf6QAaDKA8#$X7'
USERAGENT       = 'web:com.edu.lab:v1.6.0 (by /u/kei-kazuki)'
REDDITAPPID     = 'IT4XqKkD7AF8xo6elro6jw'
REDDITAPPSECRET = 'u7sO_5n37PI8fn5mL2KocA9kFfz_sg'


#Postgresql configuration
DBNAME          = 'SauceMaster'
DBUSER          = 'postgres'
DBHOST          = '127.0.0.1'
DBPASSWORD      = 'shakimom'
DBPORT          = '5432'

#Imgur configuration
IMGUR_CLIENTID      = 'c5978a36b06f083'
IMGUR_CLIENTSECRET  = 'cc47ca093ba9f2497f8a43798e3f14b7410b8fd3'

def getSignature():
    signature = '\n\n---\n\n^Tag the BOT to check reposts | Link {anime}, <manga>, ]LN[, |VN| | [Subreddit](https://www.reddit.com/r/SauceSharingCommunity/) | [FAQ](https://www.reddit.com/r/SauceSharingCommunity/wiki/index/saucesharingbot)'
    return signature.replace(' ', '&#32;')
