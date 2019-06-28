import json
import os
import sys
import threading

from math import ceil

from setting import Setting
import time
import requests
import random
import re


class PixivDaily(object):
    def __init__(self, setting):
        self.setting = setting
        self.session = requests.session()
        self.isrunning = False

    def login(self):
        data = {
            'pixiv_id': self.setting.pixiv_id,
            'password': self.setting.password,
            'source': 'account',
            'return_to': 'https://www.pixiv.net/',
        }
        user_agent = random.choice(self.setting.user_agent_list)
        header = {'User-Agent': user_agent, 'Accept-language': self.setting.language}
        try:
            res = self.session.get(self.setting.login_path, headers=header, timeout=self.setting.timeout)
            res.raise_for_status()
            form = re.compile('"pixivAccount.postKey":"[^"]+')
            data['post_key'] = re.findall(form, res.text)[0].split('"')[-1]
            time.sleep(1)
            res = self.session.post(self.setting.post_login_path, data=data, headers=header)
            res.raise_for_status()
        except:
            self.setting.logInfo("Login error, please try again")
            return False
        header['Referer'] = 'https://www.pixiv.net/'
        res = self.session.get(self.setting.check_login_path, headers=header, allow_redirects=False)
        if not re.findall(r'<title>\[pixiv\] 设置 - 用户资料</title>', res.text):
            self.setting.logInfo("Login error, please check the password or username")
            return False
        self.setting.logInfo('Login success')
        return True

    def getHTML(self, url):
        # 随机选择一个伪装user-agent
        user_agent = random.choice(self.setting.user_agent_list)
        # 获得网页访问语言配置
        language = self.setting.language
        # 传递给header
        header = {'User-Agent': user_agent, 'Accept-Language': language}
        try:
            r = requests.get(url, headers=header, timeout=self.setting.timeout)  # 连接超时时间设置
            r.raise_for_status()  # 访问失败则抛出异常
            return r.text
        except:
            # 若捕获异常说明图片主页信息访问失败,保存爬虫记录并返回空字符串
            self.setting.logInfo("单张图片信息主页访问异常！可能网络连接已中断！")
            # self.saveSetting()
            return ""

    def getURL_fromPage(self, page_url):
        # 访问搜索结果的某一页
        user_agent = random.choice(self.setting.user_agent_list)
        header = {'User-Agent' : user_agent, 'Accept-Language' : self.setting.language}
        try:
            r = self.session.get(page_url, headers = header, timeout = self.setting.timeout)  # 连接超时时间设置
            r.raise_for_status()
        except:
            self.setting.logInfo("搜索结果网页访问异常！可能网络连接已中断！")
            self.saveSetting()
            sys.exit(0)
        # 配置检索本页图片链接的正则表达式格式
        url_form = re.compile(r'https:\\/\\/i.pximg.net\\/c\\/240x240\\/img-master\\/img\\/\d+\\/\d+\\/\d+\\/\d+\\/\d+\\/\d+\\/\d+_p0_master1200.jpg')
        # 根据正则表达式提取出本页所有符合格式的图片链接，列表形式:[url1, url2,]
        url_list = re.findall(url_form, r.text)
        url_list = [re.sub(r'\\', '', url) for url in url_list]
        # 将所有链接加入到爬虫的未访问链接字典,并设置每个链接的值为0
        limit = 0
        for url in url_list:
            limit += 1
            self.setting.urls_waitting[url] = 0
            if limit == 10:
                break
        # # 根据搜索结果的某一页的信息获取检索结果图片总数，并计算出总页数(一页40张)
        # self.setting.total_find_pictures = int(re.findall('<span class="count-badge">\d+', r.text)[0].split('>')[-1])
        # self.setting.lenpage = ceil(self.setting.total_find_pictures / 40)
        # # 总页数不能超过网页允许普通用户查看的总页数(默认设置的1000)
        # if self.setting.lenpage > self.setting.max_lenpage:
        #     self.setting.lenpage = self.setting.max_lenpage
        return url_list

    def checkURL(self, url):
        id = url[65:-18]  # 获得图片id
        refer = self.setting.refer + id  # 获得图片主页地址
        picture_text = self.getHTML(refer)  # 得到图片主页文本
        if not picture_text:  # 若文本是空的说明网页访问失败
            self.isrunning = False  # 把爬虫运行状态改为False，准备退出爬虫
            self.setting.working_thread -= 1  # 终止该线程
            return
        # 查找该图片的喜爱数或点赞数
        likecount = re.findall(r'"likeCount":\d+', picture_text)
        if likecount:  # 若查找到了喜爱数
            likecount = int(likecount[0].split(':')[-1])
        else:  # 若没有喜爱数信息,则查找点赞数信息代替喜爱数信息
            likecount = re.findall(r'</span><span class="views">\d+', picture_text)
            likecount = int(likecount[-1].split('>')[-1])
        # 若设置了打印图片喜爱/点赞数，则打印
        if self.setting.likecount_visible:
            self.setting.logInfo("likecount = %d" % likecount)
        # 若图片喜爱/点赞数达到阈值
        if likecount >= self.setting.low:
            # 若图片id在已下载图片字典中不存在,则下载保存
            if id not in self.setting.picture_dic:
                # 若下载图片异常,则将爬虫运行状态设置为False,退出线程
                if not self.getPicture(url, refer, likecount, id):
                    self.isrunning = False
                    self.setting.working_thread -= 1
                    return
            else:
                self.setting.urls_waitting.pop(url)
        # 若图片喜爱/点赞数小于阈值
        else:
            try:
                self.setting.urls_waitting.pop(url)  # 从待处理的图片链接字典中删除该图片
            except:
                pass
        # 若以上流程都未出错,则该线程正常结束,更新数据
        self.setting.finished_thread += 1
        self.setting.total_browsed_pictures += 1
        self.setting.working_thread -= 1

    # 下载保存原始高清图片
    def getPicture(self, url, refer, likecount, id):
        # 以下几行是为了拼接url和refer链接得到高清图片的地址
        user_agent_list = self.setting.user_agent_list
        user_agent = random.choice(user_agent_list)
        figname = self.setting.fig + url[45:-15]
        # 如果下载图片不完整则重新下载图片
        while True:
            # 依次尝试访问以jpg, png和gif为后缀的地址
            figurl = figname + '.jpg'
            header = {'User-Agent': user_agent, 'Referer': refer}
            try:
                r = self.session.get(figurl, headers=header, timeout=self.setting.timeout)  # 连接超时时间设置
                r.raise_for_status()
            except:
                figurl = figname + '.png'
                try:
                    r = self.session.get(figurl, headers=header, timeout=self.setting.timeout)  # 连接超时时间设置
                    r.raise_for_status()
                except:
                    figurl = figname + '.gif'
                    try:
                        r = self.session.get(figurl, headers=header, timeout=self.setting.timeout)  # 连接超时时间设置
                        r.raise_for_status()
                    except:
                        # TODO 若以上三种后缀都不对,则可能下载图片过程中网络中断,或者是其它后缀,此处可能会出bug
                        self.setting.logInfo("图片下载异常！可能网络连接已中断！")
                        # print(refer)
                        # self.saveSetting()
                        return False
            pictureType = self.checkPicture(r.content)
            if pictureType:  # 如果下载图片完整
                # 图片名字为likecount + 图片id + 后缀;  filename = 路径 + 图片名字
                filename = os.path.join('daily', str(likecount) + '_' + id + pictureType)
                # 保存图片
                with open(filename, 'wb') as f:
                    f.write(r.content)
                # 如果是更新状态,则在更新文件夹也保存
                if self.setting.is_updating:
                    filename = os.path.join(self.setting.update_dir, str(likecount) + '_' + id + pictureType)
                    with open(filename, 'wb') as f:
                        f.write(r.content)
                # 从待处理的图片链接字典中删除本图片,更新并保存记录信息
                self.setting.logInfo("成功下载一张图片: " + filename + "  喜爱数为: " + str(likecount))
                self.setting.total_download += 1
                try:
                    self.setting.urls_waitting.pop(url)
                except:
                    pass
                # 把刚下载的图片保存到已下载的图片字典中,格式为{picture1_id : likecount1, picture2_id : likecount2}
                self.setting.picture_dic[id] = likecount
                self.saveSetting()
                return True
            self.setting.logInfo("下载的图片不完整,正在重新下载！")
            time.sleep(1)  # 休眠1s再重新访问，防止访问太频繁被识别出来是爬虫

    # 检查服务器返回的二进制文件是否完整,若完整，返回图片类型，否则返回空字符串
    def checkPicture(self, bitfile):
        if bytes([bitfile[-1]]) == b";":
            return '.gif'
        elif bytes([bitfile[-1]]) == b'\xd9':
            if bytes([bitfile[-2]]) == b'\xff':
                return '.jpg'
        elif bytes([bitfile[-1]]) == b'\x82':
            if bytes([bitfile[-2]]) == b'`':
                return '.png'
        return ""

    # 保存当前状态
    def saveSetting(self):
        # 线程锁把下边操作先锁上，防止不同线程同时访问同一个文件夹，导致数据混乱
        with self.setting.lock:
            # 存储未处理的图片  字典格式{url1 : 0, url2 : 0, }
            with open(self.setting.urls_waitting_path, 'w', encoding='utf8') as f:
                json.dump(self.setting.urls_waitting, f, ensure_ascii=False)
            # 存储已经下载的图片   字典格式{picture1_id : likecount1, picture2_id : likecount2}
            with open(self.setting.pic_dic_path, 'w', encoding='utf8') as f:
                json.dump(self.setting.picture_dic, f, ensure_ascii=False)
            # 存储运行状态参数(当前页面,总浏览数,总下载数,检索结果页面总数，检索出的图片总数,完成状态)
            with open(self.setting.pagenum_path, 'w', encoding='utf8') as f:
                f.write(str(self.setting.pagenum) + " " +
                        str(self.setting.total_browsed_pictures) + " " +
                        str(self.setting.total_download) + " " +
                        str(self.setting.lenpage) + " " +
                        str(self.setting.total_find_pictures) + " " +
                        str(self.setting.finished))
            self.setting.logInfo("当前爬取状态已成功保存!")

    # 对每一页的图片链接列表挨个爬取
    def crawl_url_list(self, url_list):
        length = len(url_list)  # 列表中链接总个数
        for i, url in enumerate(url_list):  # 对列表中每一个链接
            # 以下循环监听爬虫状态 以及 等待分配可用线程
            while True:
                # 如果爬虫异常终止 并且 所有线程都运行结束
                if not self.isrunning and not self.setting.working_thread:
                    self.saveSetting()
                    sys.exit(0)  # 退出爬虫并抛出异常
                # 如果爬虫正常运行 并且 存在空闲线程 则退出监听状态
                if self.isrunning and self.setting.working_thread < self.setting.max_thread:
                    break
                # 若程序正常运行  且没有空闲线程  则休眠self.setting.sleep(默认0.5s)时间之后，再次查询
                time.sleep(self.setting.sleep)
            t = threading.Thread(target=self.checkURL, args=(url,))  # 分配线程
            self.setting.working_thread += 1  # 运行中的线程数加1
            t.start()  # 开始运行线程
            # 每启动一个新线程就打印当前的状态信息
            self.setting.logInfo("浏览:%d | 下载:%d | 检索结果:%d || "
                                 "本页进度%2d | %2d || 页面进度:"
                                 "%d | %d || 已完成:%d | 工作中:%d"
                                 % (self.setting.total_browsed_pictures, self.setting.total_download,
                                    self.setting.total_find_pictures,
                                    i + 1, length, self.setting.pagenum, self.setting.lenpage,
                                    self.setting.finished_thread, self.setting.working_thread))

    # 爬虫主函数
    def run(self):
        # 登录
        if self.login():
            self.isrunning = True  # 若成功，则将爬虫运行状态改为True,表示正常运行
        else:
            sys.exit(0)  # 若不成功，退出爬虫，并抛出异常
        if self.setting.urls_waitting:  # 如果历史记录中有未访问的图片网页，则优先处理这些
            self.crawl_url_list(list(self.setting.urls_waitting.keys()))  # 爬取历史记录中未处理的网页
            # self.setting.pagenum += 1  # 本页爬完，准备访问下一页
            self.saveSetting()  # 存档
        # word = "%20".join(self.setting.keyword.split())  # 多个检索关键词用%20拼接
        while self.setting.pagenum <= self.setting.lenpage:  # 若爬完所有页面，则终止
            # page_url = self.setting.website + word + self.setting.page + str(self.setting.pagenum)  # 得到检索结果某一页的地址
            page_url = self.setting.daily_site
            url_list = self.getURL_fromPage(page_url)  # 爬取检索结果的某页，并从页面中提取出所有图片(约39或40个，视频跳过不管)
            self.saveSetting()  # 每访问一次新的页面后保存记录
            self.crawl_url_list(url_list)  # 爬取该页的所有图片
            # self.setting.pagenum += 1  # 本页爬完，准备访问下一页
        # 等待线程都运行结束，若爬完所有网页，将self.finished改为True,保存状态并退出
        while self.setting.working_thread:
            time.sleep(self.setting.sleep)
        if self.isrunning:
            self.setting.finished = 1
        self.saveSetting()
        sys.exit(0)


# 操作系统调用本程序入口
if __name__ == '__main__':
    # 获得配置
    setting = Setting()
    # 是否初始化
    if setting.cleanDir:  # 若初始化
        setting.clean()  # 执行初始化
    # 是否更新
    if setting.is_updating:
        setting.update()
        setting.logInfo("当前是更新状态!更新页数为: %d" % setting.max_lenpage)
    else:
        setting.logInfo("当前是非更新状态!")
    setting.logInfo(("开始爬取！搜索关键词为：" + setting.keyword +
                     " | 下载阈值为: %d | 总线程数为: %d") % (setting.low, setting.max_thread))
    setting.logInfo("正在尝试第一次登录...")
    # 循环监听
    while True:
        crawler = PixivDaily(setting)  # 生成爬虫
        try:
            crawler.run()  # 执行爬虫，若登录失败或者运行过程中连接中断会抛出异常
        except:  # 捕获异常
            # 若是爬虫运行结束正常退出，则关闭该程序
            if crawler.setting.finished:
                if setting.is_updating:
                    setting.logInfo("更新结束！更新了%d张图片!" % crawler.setting.total_download)
                    os.remove(setting.update_mark)
                else:
                    setting.logInfo("爬取结束！爬取到%d张图片!" % crawler.setting.total_download)
                break
            # 若因为网络连接中断非正常退出则休眠5s再尝试重新登录
            setting.logInfo("正在尝试重新登录...")
            time.sleep(setting.restart_sleep)


