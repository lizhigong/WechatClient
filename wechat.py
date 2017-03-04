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
from collections import defaultdict
import multiprocessing
import mimetypes
from requests_toolbelt.multipart.encoder import MultipartEncoder


class WeChat:
    def __init__(self):

        self.mode = 1  # debug mode
        self.session = SafeSession()
        self.encoding = 'utf-8'
        self.resource_dir = os.path.join(os.getcwd(), 'resource')
        self.img_resource_dir = os.path.join(os.getcwd(), 'resource', 'image')
        self.voice_resource_dir = os.path.join(os.getcwd(), 'resource', 'voice')
        self.video_resource_dir = os.path.join(os.getcwd(), 'resource', 'video')
        self._check_and_create_dir()
        self.login_retry_times = 10
        self.login_retry_interval = 1  # seconds
        self.timeout = 60  # seconds
        self.sync_time_interval = 1  # seconds
        self.default_sync_host = ['webpush.wx.qq.com', 'webpush2.wx.qq.com', 'webpush.wechat.com',
                                  'webpush1.wechat.com', 'webpush2.wechat.com', 'webpush.wechatapp.com',
                                  'webpush1.wechatapp.com']  # sync check hosts
        self.default_special_accounts = ['newsapp', 'filehelper', 'weibo', 'qqmail',
                 'fmessage', 'tmessage', 'qmessage', 'qqsync', 'floatbottle',
                 'lbsapp', 'shakeapp', 'medianote', 'qqfriend', 'readerapp',
                 'blogapp', 'facebookapp', 'masssendapp', 'meishiapp',
                 'feedsapp', 'voip', 'blogappweixin', 'weixin', 'brandsessionholder',
                 'weixinreminder', 'wxid_novlwrv3lqwv11',
                 'officialaccounts',
                 'gh_22b87fa7cb3c', 'wxitil', 'userexperience_alarm',
                 'notification_messages', 'notifymessage']  # all known special accounts, always default accounts

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
        self.sync_check_host = ''
        self.media_index = 0

        self.user_info = {}  # UserName->id, NickName->nickname, HeadImgUrl
        self.account_info = {'group_member': {}, 'normal_member': {}}  # all the accounts
        # format {'group_member':{'id':{'type':'group_member', 'info':{}}, ...}, 'normal_member':{'id':{}, ...}}

        self.contact_list = []  # contacts
        self.public_list = []  # public accounts
        self.special_list = []  # special accounts
        self.group_list = []  # group chats

        self.group_members_list = {}  # members of all the group chats
        # format {'group_id':[member, member, ...]}

        self.encry_chat_room_id_list = []  # for group members' head img

    def __unicode__(self, string, encoding='utf-8'):
        if isinstance(string, str):
            return string.decode(encoding)
        elif isinstance(string, unicode):
            return string

    def _refresh_contact(self):
        self.contact_list = []
        self.public_list = []
        self.group_list = []

    def _check_and_create_dir(self):
        if not os.path.exists(self.resource_dir):
            os.makedirs(self.resource_dir)
        if not os.path.exists(self.img_resource_dir):
            os.makedirs(self.img_resource_dir)
        if not os.path.exists(self.video_resource_dir):
            os.makedirs(self.video_resource_dir)
        if not os.path.exists(self.voice_resource_dir):
            os.makedirs(self.voice_resource_dir)

    def get_display_name(self, id):
        # [TODO]
        name = 'Unknown'
        if id == self.user_info['UserName']:
            return self.user_info['NickName']  # self

        if id[:2] == '@@':
            # group chat
            name = 'Group Chat'
        else:
            # special
            for member in self.special_list:
                if member['UserName'] == id:
                    name = member['RemarkName'] if member[
                        'RemarkName'] else member['NickName']

            # public
            for member in self.public_list:
                if member['UserName'] == id:
                    name = member['RemarkName'] if member[
                        'RemarkName'] else member['NickName']

            # contact
            for member in self.contact_list:
                if member['UserName'] == id:
                    name = member['RemarkName'] if member[
                        'RemarkName'] else member['NickName']

            # group chat members

        return name

    def get_msg_image(self, msg_id):
        url = self.base_uri + '/webwxgetmsgimg?MsgID=%s&skey=%s' % (msg_id, self.skey)
        r = self.session.get(url)
        data = r.content
        fn = 'img_' + msg_id + '.jpg'
        with open(os.path.join(self.img_resource_dir, fn), 'wb') as f:
            f.write(data)
        return fn

    def get_msg_voice(self, msg_id):
        url = self.base_uri + '/webwxgetvoice?msgid=%s&skey=%s' % (msg_id, self.skey)
        r = self.session.get(url)
        data = r.content
        fn = 'voice_' + msg_id + '.mp3'
        with open(os.path.join(self.voice_resource_dir, fn), 'wb') as f:
            f.write(data)
        return fn

    def get_msg_video(self, msg_id):
        url = self.base_uri + '/webwxgetvideo?msgid=%s&skey=%s' % (msg_id, self.skey)
        headers = {
            'Range': 'bytes=0-'
        }
        r = self.session.get(url, headers=headers)
        data = r.content
        fn = 'video_' + msg_id + '.mp4'
        with open(os.path.join(self.video_resource_dir, fn), 'wb') as f:
            f.write(data)
        return fn

    def run(self):
        try:
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
                print 'get_contacts: %d contacts' % len(self.contact_list)
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

            # result = self.send_text_message('123', 'ljy')
            # print 'send_text_message to user : {r}'.format(r=result)

            # self.upload_media('siri.jpeg')
            # self.upload_media('safesession.py')
            # result = self.send_image_and_emotion_message('siri.jpeg', 'ljy')
            # print  'send_image_and_emotion_message to user : {r}'.format(r=result)

            # self.message_listener()
            listener = multiprocessing.Process(target=self.message_listener())
            listener.run()


        except KeyboardInterrupt:
            print ' command : QUIT'

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

        if sys.platform.find('darwin') >= 0:
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
            'BaseRequest'   : self.base_request,
            "Code"          : 3,
            "FromUserName"  : self.user_info['UserName'],
            "ToUserName"    : self.user_info['UserName'],
            "ClientMsgId"   : int(time.time())
        }
        r = self.session.post(url, data=json.dumps(params))
        r.encoding = self.encoding
        result = json.loads(r.text)
        return result['BaseResponse']['Ret'] == 0

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
        self._refresh_contact()

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
            'BaseRequest'   : self.base_request,
            "Count"         : len(self.group_list),
            "List"          : [{"UserName": group['UserName'], "EncryChatRoomId": ""} for group in self.group_list]
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

    def sync_check(self):  # return [retcode, selector]
        url = 'https://' + self.sync_check_host + '/cgi-bin/mmwebwx-bin/synccheck?'
        params = {
            'r': int(time.time()),
            'sid': self.sid,
            'uin': self.uin,
            'skey': self.skey,
            'deviceid': self.device_id,
            'synckey': self.sync_check_key,
            '_': int(time.time()),
        }

        r = self.session.get(url, params=params, timeout=60)
        if r == '':
            return [-1, -1]
        r.encoding = self.encoding
        data = r.text
        result = re.search(r'window.synccheck=\{retcode:"(\d+)",selector:"(\d+)"\}', data)
        retcode = result.group(1)
        selector = result.group(2)
        return [retcode, selector]

    def choose_sync_host(self):
        for host in self.default_sync_host:
            self.sync_check_host = host
            retcode = self.sync_check()[0]
            if retcode == '0':
                return True
        return False

    def sync(self):
        url = self.base_uri + '/webwxsync?sid=%s&skey=%s&lang=en_US&pass_ticket=%s' \
                              % (self.sid, self.skey, self.pass_ticket)
        params = {
            'BaseRequest'   : self.base_request,
            'SyncKey'       : self.sync_key,
            'rr'            : ~int(time.time())
        }
        r = self.session.post(url, data=json.dumps(params), timeout=60)
        if r == '':
            return None
        r.encoding = self.encoding
        result = json.loads(r.text)
        if result['BaseResponse']['Ret'] == 0:
            self.sync_key = result['SyncKey']
            self.sync_check_key = '|'.join([str(keyVal['Key']) + '_' + str(keyVal['Val'])
                                            for keyVal in self.sync_key['List']])
        return result

    def search_content(self, key, content, ft):
        if ft == 'attr':  # key is an attribution of a xml label
            result = re.search(key + '\s?=\s?"([^"<]+)"', content)
            if result:
                return result.group(1)
        elif ft == 'xml':  # key is a xml label
            result = re.search('<{0}>([^<]+)</{0}>'.format(key), content)
            if not result:
                result = re.search(
                    '<{0}><!\[CDATA\[(.*?)\]\]></{0}>'.format(key), content)
            if result:
                return result.group(1)
        return None

    def custom_message_receiver(self, msg):
        # add custom message receiver in or by inheriting this func
        print msg["msg_id"]
        print msg["hint"]
        pass

    def message_handler(self, r):
        for msg in r['AddMsgList']:
            msg_type = msg['MsgType']
            name = self.get_display_name(msg['FromUserName'])
            content = msg['Content'].replace('&lt;', '<').replace('&gt;', '>')
            msg_id = msg['MsgId']
            hint_msg = ''

            if msg_type == 1:  # text
                hint_msg = content

            elif msg_type == 3:  # image
                image = self.get_msg_image(msg_id)
                hint_msg = '%s send image: %s' % (name, image)

            elif msg_type == 34:  # voice
                voice = self.get_msg_voice(msg_id)
                hint_msg = '%s send voice: %s' % (name, voice)

            elif msg_type == 42:  # recommend card
                info = msg['RecommendInfo']
                # print('%s send you recommend:' % name)
                # print('  nickname   : %s' % info['NickName'])
                # print('  alias      : %s' % info['Alias'])
                # print('  district   : %s %s' % (info['Province'], info['City']))
                # print('  gender     : %s' % ['unknown', 'male', 'female'][info['Sex']])
            elif msg_type == 47:  # emotion
                url = self.search_content('cdnurl', content, 'attr')
                hint_msg = '%s send emotion: %s' % (name, url)

            elif msg_type == 49:  # link
                app_msg_type = defaultdict(lambda: "")
                app_msg_type.update({5: 'link', 3: 'music', 7: 'weibo'})  # red package 2001
                # print('%s share %s:' % (name, app_msg_type[msg['AppMsgType']]))
                # print('  title          : %s' % msg['FileName'])
                # print('  description    : %s' % self.search_content('des', content, 'xml'))
                # print('  link           : %s' % msg['Url'])
                # print('  from           : %s' % self.search_content('appname', content, 'xml'))
                card = {
                    'title': msg['FileName'],
                    'description': self.search_content('des', content, 'xml'),
                    'url': msg['Url'],
                    'appname': self.search_content('appname', content, 'xml')
                }
                hint_msg = '%s shared %s: %s' % (name, app_msg_type[msg['AppMsgType']], json.dumps(card))

            elif msg_type == 51:  # init message
                #hint_msg = '  contact init'
                return

            elif msg_type == 62:  # video
                video = self.get_msg_video(msg_id)
                hint_msg = '%s send video : %s' % (name, video)

            elif msg_type == 10002:  # recall
                recall_msg_content = json.dumps(msg)
                result = re.search('&lt;msgid&gt;([^&lt;]+)&lt;/msgid&gt;', recall_msg_content)
                hint_msg = 'recalled message id: %s' % result.group(1)

            else:  # unknown
                hint_msg = 'message type: %d, unknown message(maybe view it on phone)' % msg['MsgType']

            # add custom message receiver
            msg = {
                "msg_type_id"   :   msg_type,
                "msg_id"        :   msg_id,
                "user_id"       :   msg['FromUserName'],
                "to_user_id"    :   msg['ToUserName'],
                "hint"          :    hint_msg
            }
            self.custom_message_receiver(msg)

    def message_listener(self):
        self.choose_sync_host()
        while True:
            current_check_time = time.time()
            [retcode, selector] = self.sync_check()
            if retcode == '1100':  # logout / fail to login
                break
            elif retcode == '1101':  # login at another device
                break
            elif retcode == '0':
                if selector == '2':  # new message
                    r = self.sync()
                    if r is not None:
                        self.message_handler(r)
                elif selector == '3':  #
                    r = self.sync()
                    if r is not None:
                        self.message_handler(r)
                elif selector == '4':  # contact update
                    r = self.sync()
                    if r is not None:
                        self.get_contact()
                elif selector == '6':  #
                    r = self.sync()
                    if r is not None:
                        self.message_handler(r)
                elif selector == '7':  # operate on phone
                    r = self.sync()
                    if r is not None:
                        self.message_handler(r)
                elif selector == '0':  # none
                    pass
                else:
                    print 'Unknown error'
            current_check_time = time.time() - current_check_time
            if current_check_time < self.sync_time_interval:
                time.sleep(self.sync_time_interval - current_check_time)

    def send_text_message(self, content, dst):
        content = self.__unicode__(content)
        msg_id = str(int(time.time() * 1000)) + str(random.random())[:5].replace('.', '')
        # print msg_id
        if dst == '':
            return False
        dst = self.__unicode__(dst)
        dst_id = ''
        for contact in self.contact_list:
            if 'RemarkName' in contact and contact['RemarkName'] == dst:
                dst_id = contact['UserName']
            if 'NickName' in contact and contact['NickName'] == dst:
                dst_id = contact['UserName']
            if 'DisplayName' in contact and contact['DisplayName'] == dst:
                dst_id = contact['UserName']
        for group in self.group_list:
            if 'RemarkName' in group and group['RemarkName'] == dst:
                dst_id = group['UserName']
            if 'NickName' in group and group['NickName'] == dst:
                dst_id = group['UserName']
            if 'DisplayName' in group and group['DisplayName'] == dst:
                dst_id = group['UserName']
        if dst_id == '':
            return False

        url = self.base_uri + '/webwxsendmsg?pass_ticket=%s' % self.pass_ticket
        params = {
            'BaseRequest': self.base_request,
            'Msg': {
                "Type": 1,  # text
                "Content": content,
                "FromUserName": self.user_info['UserName'],
                "ToUserName": dst_id,
                "LocalID": msg_id,
                "ClientMsgId": msg_id
            }
        }
        result = self.session.post(url, data=json.dumps(params).encode(self.encoding))
        # print result.json()
        if result == '':
            return False
        return result.json()['BaseResponse']['Ret'] == 0

    def upload_media(self, path):
        if not os.path.exists(path=path):
            return None

        file_len = str(os.path.getsize(path))
        file_type = mimetypes.guess_type(path, strict=False)[0]
        media_type = ''
        if file_type.split('/')[0] == 'image':
            media_type = 'pic'
        else:
            media_type = 'doc'
        # print media_type
        last_modified_date = time.strftime('%m/%d/%Y, %H:%M:%S GMT+0800 (CST)')
        client_media_id = str(int(time.time() * 1000)) + str(random.random())[:5].replace('.', '')

        url = 'https://file.'+self.base_host+'/cgi-bin/mmwebwx-bin/webwxuploadmedia?f=json'
        upload_media_request = {
            'BaseRequest': self.base_request,
            'ClientMediaId': client_media_id,
            'TotalLen': file_len,
            'StartPos': 0,
            'DataLen': file_len,
            'MediaType': 4,
        }

        params = {
            'id': (None, 'WU_FILE_%s' % str(self.media_index)),
            'name': (None, os.path.basename(path)),
            'type': (None, file_type),
            'lastModifiedDate': (None, last_modified_date),
            'size': (None, file_len),
            'mediatype': (None, media_type),
            'uploadmediarequest': (None, json.dumps(upload_media_request)),
            'webwx_data_ticket': (None, self.session.cookies['webwx_data_ticket']),
            'pass_ticket': (None, self.pass_ticket),
            'filename': (os.path.basename(path), open(path, 'rb'), file_type.split('/')[1]),
        }
        r = self.session.post(url, files=params)
        self.media_index += 1
        # print r.json()
        if r == '':
            return None
        media_id = json.loads(r.text)['MediaId']
        return media_id

    def send_image_and_emotion_message(self, path, dst):
        media_id = self.upload_media(path)
        if media_id is None:
            return False
        if dst == '':
            return False
        dst = self.__unicode__(dst)
        dst_id = ''
        for contact in self.contact_list:
            if 'RemarkName' in contact and contact['RemarkName'] == dst:
                dst_id = contact['UserName']
            if 'NickName' in contact and contact['NickName'] == dst:
                dst_id = contact['UserName']
            if 'DisplayName' in contact and contact['DisplayName'] == dst:
                dst_id = contact['UserName']
        for group in self.group_list:
            if 'RemarkName' in group and group['RemarkName'] == dst:
                dst_id = group['UserName']
            if 'NickName' in group and group['NickName'] == dst:
                dst_id = group['UserName']
            if 'DisplayName' in group and group['DisplayName'] == dst:
                dst_id = group['UserName']
        if dst_id == '':
            return False

        url = self.base_uri + '/webwxsendmsgimg?fun=async&f=json'
        params = {
            'BaseRequest': self.base_request,
            'Msg': {
                'Type': 3,
                'MediaId': media_id,
                'FromUserName': self.user_info['UserName'],
                'ToUserName': dst_id,
                'LocalID': str(time.time() * 1e7),
                'ClientMsgId': str(time.time() * 1e7),
            },
        }
        if path[-4:] == '.gif':
            url = self.base_uri + '/webwxsendemoticon?fun=sys'
            params['Msg']['Type'] = 47
            params['Msg']['EmojiFlag'] = 2

        r = self.session.post(url, data=json.dumps(params))
        if r == '':
            return False
        if json.loads(r.text)['BaseResponse']['Ret'] == 0:
            return True
        else:
            return False
