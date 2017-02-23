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

    def run(self):
        self.get_uuid()
        self.get_qrcode(os.path.join(self.resource_dir, 'qr.png'))

        result = self.wait_for_login()
        print result

        result = self.sync_login()
        print result


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
        doc = xml.dom.minidom.parseString(data)
        root = doc.documentElement

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

    def format_username(user_name):
        return {"UserName": user_name, "EncryChatRoomId": ""}