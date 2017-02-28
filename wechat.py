# coding: utf-8

import os
import sys
import webbrowser
import pyqrcode
import time
import re
import random
import xml.dom.minidom
from safesession import SafeSession
import json


class WeChat:
    def __init__(self):

        self.mode = 1  # debug mode
        self.session = SafeSession()
        self.encoding = 'utf-8'
        self.resource_dir = os.path.join(os.getcwd(),'temp')
        self.login_retry_times = 10
        self.login_retry_interval = 1  # seconds

        self.uuid = ''
        self.redirect_uri = ''
        self.base_uri = ''
        self.base_host = ''
        self.uin = ''
        self.sid = ''
        self.skey = ''
        self.pass_ticket = ''
        self.device_id = 'e' + repr(random.random())[2:17]
        self.base_request = {}
        self.sync_key = []
        self.sync_check_key = ''  # formatted sync key for sync check

        self.user_info = {}  # UserName->id, NickName->nickname, HeadImgUrl
        self.account_info = {'group_member': {}, 'normal_member': {}}  # all the accounts
        # format {'group_member':{'id':{'type':'group_member', 'info':{}}, ...}, 'normal_member':{'id':{}, ...}}

        self.contact_list = []  # contacts
        self.public_list = []  # public accounts
        self.special_list = []  # special accounts
        self.default_special_accounts = ['newsapp', 'filehelper', 'weibo', 'qqmail',
                 'fmessage', 'tmessage', 'qmessage', 'qqsync', 'floatbottle',
                 'lbsapp', 'shakeapp', 'medianote', 'qqfriend', 'readerapp',
                 'blogapp', 'facebookapp', 'masssendapp', 'meishiapp',
                 'feedsapp', 'voip', 'blogappweixin', 'weixin', 'brandsessionholder',
                 'weixinreminder', 'wxid_novlwrv3lqwv11',
                 'officialaccounts',
                 'gh_22b87fa7cb3c', 'wxitil', 'userexperience_alarm',
                 'notification_messages', 'notifymessage']  # all known special accounts, always default accounts
        self.group_list = []  # group chats

        self.group_members_list = {}  # members of all the group chats
        # format {'group_id':[member, member, ...]}

        self.encry_chat_room_id_list = []  # for group members' head img


    def run(self):
        self.get_uuid()
        self.get_qrcode(os.path.join(self.resource_dir, 'qr.png'))

        result = self.wait_for_login()
        print 'wait_for_login : {r}'.format(r=result)

        result = self.sync_login()
        print 'sync_login : {r}'.format(r=result)

        result = self.wechat_init()
        print 'wechat_init : {r}'.format(r=result)

        result = self.status_notify()
        print 'status_notify : {r}'.format(r=result)

        if self.get_contact():
            print 'get_contacts:'
            print '%d contacts' % len(self.contact_list)
            # print self.contact_list
            # print self.group_members_list
            with open(os.path.join(self.resource_dir, 'contact_list.json'), 'w') as f:
                f.write(json.dumps(self.contact_list))
            with open(os.path.join(self.resource_dir, 'special_list.json'), 'w') as f:
                f.write(json.dumps(self.special_list))
            with open(os.path.join(self.resource_dir, 'group_list.json'), 'w') as f:
                f.write(json.dumps(self.group_list))
            with open(os.path.join(self.resource_dir, 'public_list.json'), 'w') as f:
                f.write(json.dumps(self.public_list))
            with open(os.path.join(self.resource_dir, 'group_list.json'), 'w') as f:
                f.write(json.dumps(self.group_list))
            with open(os.path.join(self.resource_dir, 'group_members_list.json'), 'w') as f:
                f.write(json.dumps(self.group_members_list))
            with open(os.path.join(self.resource_dir, 'account_info.json'), 'w') as f:
                f.write(json.dumps(self.account_info))

    def get_uuid(self):
        url = 'https://login.weixin.qq.com/jslogin'
        params = {
            'appid' : 'wx782c26e4c19acffb',     # web微信
                                                # wxeb7ec651dd0aefa9  微信网页版
            'fun'   : 'new',
            'lang'  : 'zh_CN',
            '_'     : int(time.time()) * 1000 + random.randint(1, 999),
        }

        r = self.session.get(url, params=params)
        r.encoding = self.encoding
        pattern = r'window.QRLogin.code = (\d+); window.QRLogin.uuid = "(\S+?)"'
        result = re.search(pattern, r.text)
        if result:
            self.uuid = result.group(2)
            return result.group(1) == '200'
        return False

    def get_qrcode(self, qrcode_path):
        qr = pyqrcode.create('https://login.weixin.qq.com/l/' + self.uuid)
        qr.png(qrcode_path, scale=8)
        if sys.version_info >= (3, 3):
            from shlex import quote
        else:
            from pipes import quote

        if sys.platform == "darwin":
            command = "open -a /Applications/Preview.app %s&" % quote(qrcode_path)
            os.system(command)
        else:
            webbrowser.open(qrcode_path)

    def wait_for_login(self):
        # tip = 1, 未扫描,
        #     201: scaned
        #     408: timeout
        # tip = 0, 已扫描,
        #     200: confirmed
        url = 'https://login.weixin.qq.com/cgi-bin/mmwebwx-bin/login'
        params = {
            'tip' : 1,
            'uuid': self.uuid,
            '_'   : int(time.time())
        }

        retry_time = 0
        code = 'unknown'
        data = ''
        while retry_time < self.login_retry_times:
            r = self.session.get(url, params=params)
            r.encoding = self.encoding
            data = r.text
            pattern = r'window.code=(\d+);'
            result = re.search(pattern, data)
            code = result.group(1)
            if code == '200':
                pattern = r'window.redirect_uri="(\S+?)";'
                result = re.search(pattern, data)
                redirect_uri = result.group(1) + '&fun=new'
                self.redirect_uri = redirect_uri
                self.base_uri = redirect_uri[:redirect_uri.rfind('/')]  # https://wx.qq.com/cgi-bin/mmwebwx-bin
                temp_host = self.base_uri[8:]
                self.base_host = temp_host[:temp_host.find("/")]  # wx.qq.com
                return code
            elif code == '201':
                print '[DEBUG]scanned'
                params['tip'] = 0
            elif code == '408':
                print '[DEBUG]timeout-retry time: %s' % (retry_time + 1)
                params['tip'] = 1
                retry_time += 1
                time.sleep(self.login_retry_interval)
            else:
                print '[DEBUG]unknown errors'
                params['tip'] = 1
                retry_time += 1
                time.sleep(self.login_retry_interval)
        return code

    def sync_login(self):
        r = self.session.get(self.redirect_uri)
            # https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage?ticket=xxx&uuid=xxx&lang=xxx&scan=xxx&fun=new
        r.encoding = 'utf-8'
        data = r.text
        root = xml.dom.minidom.parseString(data).documentElement

        for node in root.childNodes:
            if node.nodeName == 'wxuin':
                self.uin = node.childNodes[0].data
            elif node.nodeName == 'wxsid':
                self.sid = node.childNodes[0].data
            elif node.nodeName == 'skey':
                self.skey = node.childNodes[0].data
            elif node.nodeName == 'pass_ticket':
                self.pass_ticket = node.childNodes[0].data

        if '' in (self.skey, self.sid, self.uin, self.pass_ticket):
            return False

        self.base_request = {
            'Uin': self.uin,
            'Sid': self.sid,
            'Skey': self.skey,
            'DeviceID': self.device_id,
        }
        return True

    def wechat_init(self):
        url = self.base_uri + '/webwxinit?r=%i&lang=en_US&pass_ticket=%s&skey=%s' \
                              % (int(time.time()), self.pass_ticket, self.skey)
        params = {
            'BaseRequest': self.base_request
        }
        r = self.session.post(url, data=json.dumps(params))
        r.encoding = self.encoding
        result = json.loads(r.text)
        self.sync_key = result['SyncKey']
        self.sync_check_key = '|'.join([str(keyVal['Key']) + '_' + str(keyVal['Val'])
                                        for keyVal in self.sync_key['List']])
        self.user_info = result['User']
        #print self.user_info
        return result['BaseResponse']['Ret'] == 0

    def status_notify(self):
        url = self.base_uri + '/webwxstatusnotify?lang=zh_CN&pass_ticket=%s' % self.pass_ticket
        params = {
            'BaseRequest': self.base_request,
            "Code": 3,
            "FromUserName": self.user_info['UserName'],
            "ToUserName": self.user_info['UserName'],
            "ClientMsgId": int(time.time())
        }
        r = self.session.post(url, data=json.dumps(params))
        r.encoding = self.encoding
        result = json.loads(r.text)
        return result['BaseResponse']['Ret'] == 0

    def refresh_contact(self):
        self.contact_list = []
        self.public_list = []
        self.group_list = []

    def get_contact(self):
        url = self.base_uri + '/webwxgetcontact?pass_ticket=%s&skey=%s&r=%s' \
                              % (self.pass_ticket, self.skey, int(time.time()))
        params = {}
        r = self.session.post(url, data=json.dumps(params))
        if r == '':
            return False

        r.encoding = self.encoding
        result = json.loads(r.text)
        self.group_members_list = result['MemberList']
        self.refresh_contact()

        for contact in self.group_members_list:
            if contact['VerifyFlag'] & 8 != 0:
                self.public_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'public', 'info': contact}
            elif contact['UserName'] in self.default_special_accounts:
                self.special_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'special', 'info': contact}
            elif contact['UserName'].find('@@') != -1:
                self.group_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'group', 'info': contact}
            elif contact['UserName'] == self.user_info['UserName']:
                self.account_info['normal_member'][contact['UserName']] = {'type': 'self', 'info': contact}
            else:
                self.contact_list.append(contact)
                self.account_info['normal_member'][contact['UserName']] = {'type': 'unknown', 'info': contact}

        url = self.base_uri + '/webwxbatchgetcontact?type=ex&r=%s&pass_ticket=%s' % (int(time.time()), self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            "Count": len(self.group_list),
            "List": [{"UserName": group['UserName'], "EncryChatRoomId": ""} for group in self.group_list]
        }
        r = self.session.post(url, data=json.dumps(params))
        r.encoding = self.encoding
        dic = json.loads(r.text)
        group_members = {}
        encry_chat_room_id = {}
        for group in dic['ContactList']:
            gid = group['UserName']
            members = group['MemberList']
            group_members[gid] = members
            encry_chat_room_id[gid] = group['EncryChatRoomId']
        self.group_members_list = group_members
        self.encry_chat_room_id_list = encry_chat_room_id

        for group in self.group_members_list:
            for member in self.group_members_list[group]:
                if member['UserName'] not in self.account_info:
                    self.account_info['group_member'][member['UserName']] = \
                        {'type': 'group_member', 'info': member, 'group': group}

        return True

    def sync(self):
        url = self.base_uri + '/webwxsync?sid=%s&skey=%s&lang=en_US&pass_ticket=%s' \
                              % (self.sid, self.skey, self.pass_ticket)
        params = {
            'BaseRequest': self.base_request,
            'SyncKey': self.sync_key,
            'rr': ~int(time.time())
        }
        try:
            r = self.session.post(url, data=json.dumps(params), timeout=60)
            r.encoding = self.encoding
            result = json.loads(r.text)
            if result['BaseResponse']['Ret'] == 0:
                self.sync_key = result['SyncKey']
                self.sync_check_key = '|'.join([str(keyVal['Key']) + '_' + str(keyVal['Val'])
                                              for keyVal in self.sync_key['List']])
            return result
        except:
            return None

    def format_username(user_name):
        return {"UserName": user_name, "EncryChatRoomId": ""}