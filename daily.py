import time

from setting import Setting
import requests
import random
import re

class PixivDaily(object):
    def __init__(self,setting):
        self.setting = setting
        self.session = requests.session()
        self.isrunning = False

    def login(self):
        data = {
            'pixiv_id' : self.setting.pixiv_id,
            'password' : self.setting.password,
            'source' : 'account',
            'return_to' : 'https://www.pixiv.net/',
        }
        user_agent = random.choice(self.setting.user_agent_list)
        header = {'User-Agent' : user_agent, 'Accept-language' : self.setting.language}
        try:
            res = self.session.get(self.setting.login_path,header = header, timeout = self.setting.timeout)
            res.raise_for_status()
            form = re.compile('"pixivAccount.postKey":"[^"]+')
            data['post_key'] = re.findall(form, res.text)[0].split('"')[-1]
            time.sleep(1)
            res = self.session.post()
        except:
