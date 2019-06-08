# -*- coding=utf-8 -*-

import requests as rq
import re
import random
import os
import threading
import json
import time
from setting import Setting
import sys
from math import ceil


# 爬虫主体
class MyPixivCrawler(object):
    # 初始化爬虫，在爬虫对象创建之时自动调用
    def __init__(self):
        self.setting = Setting()    # 爬虫配置类
        self.session = rq.session() # 爬虫维持一个会话用于登录网站，记录cookie信息, 并访问检索结果的每一页
        self.isrunning = False      # 记录当前爬虫的运行状态，初始为False,登录成功后改为True，子线程出现异常会改为False
        self.restore()              # 恢复记录

    # 恢复历史记录
    def restore(self):
        # 若存在历史记录文件则恢复历史记录
        if os.path.exists(self.setting.pic_dic_path):   # 若存在下载的图片字典文件(说明有历史记录)
            # 恢复历史记录中未处理的图片链接  字典格式{url1 : 0, url2 : 0, }
            with open(self.setting.urls_waitting_path, 'r', encoding='utf8') as f:
                self.setting.urls_waitting = json.load(f)
            # 恢复当前已下载的图片   字典格式 {picture1_id : likecount1, picture2_id : likecount2}
            with open(self.setting.pic_dic_path, 'r', encoding='utf8') as f:
                self.setting.picture_dic = json.load(f)
            # 恢复一些运行状态参数  他们保存在一个文件('pagenum.txt')里边，用空格隔开
            with open(self.setting.pagenum_path, 'r', encoding='utf8') as f:
                r = f.read().split()        # f.read()得到文件字符串, split把字符串分开成一个列表,里边5个元素
            self.setting.pagenum = int(r[0])        # 当前访问的检索结果页面数
            self.setting.total_browsed_pictures = int(r[1])     # 历史浏览过的图片总数
            self.setting.total_download = int(r[2])         # 历史下载的图片总数
            self.setting.lenpage = int(r[3])               # 检索结果的页面总数
            self.setting.total_find_pictures = int(r[4])    # 检索出的图片总数

    # 登录p站
    def login(self):
        # 用于提交给网站的登录数据
        data = {
            'pixiv_id' : self.setting.pixiv_id,
            'password' : self.setting.password,
            'source' : 'accounts',
            'return_to' : 'https://www.pixiv.net/',
        }
        user_agent = random.choice(self.setting.user_agent_list)    # 随机选一个user-agent伪装爬虫
        header = {'User-Agent' : user_agent, 'Accept-Language' : self.setting.language} # 请求头
        try:
            # 首先用会话访问登录网址并抓取网页  r是返回的响应
            r = self.session.get(self.setting.login_path, headers = header, timeout = self.setting.timeout)  # 连接超时时间设置为10s
            # 若访问失败则下一句抛出状态异常(若成功访问r的状态值为200,不会抛出异常,其他值都会抛出异常)
            r.raise_for_status()
            # 设置正则表示式用于检索出  登录数据中的post_key数据
            form = re.compile('"pixivAccount.postKey":"[^"]+')
            # 完善登录数据
            data['post_key'] = re.findall(form, r.text)[0].split('"')[-1]
            # 休眠1s防止访问太频繁
            time.sleep(1)
            # 用会话访问登录信息提交网址  并提交登录数据 r是返回的响应
            # 若登录成功,则cookie信息会保存在session中, 可供程序访问检索结果页面
            r = self.session.post(url=self.setting.post_login_path, data = data, headers = header)
            # 若访问失败则下一句抛出异常
            r.raise_for_status()
        except:
            # 若出现异常说明登录异常,返回False表示登录失败
            self.setting.logInfo("登录网页访问异常！可能网络连接已中断！")
            return False
        # 检验是否登录成功,因为即使密码输错也不会报异常,所以访问一个登录以后才能访问的网址(网页中有"设置-用户资料"字符串)
        # 若未登录访问该防止会跳转到登录界面,就没有"设置 - 用户资料"字段
        header['Referer'] = 'https://www.pixiv.net/'   # 请求头的参照信息,表示下边要爬取(get)的网页是从referer网址跳转访问的
        r = self.session.get(self.setting.check_login_path, headers = header, allow_redirects = False)
        # 查找响应的网页是否存在"设置 - 用户资料"字符串，若存在,则登录成功,否则登录失败
        if not re.findall(r'<title>\[pixiv\] 设置 - 用户资料</title>', r.text):
            self.setting.logInfo("登录失败!请检查邮箱和密码！")
            # print(r.status_code)
            return False
        self.setting.logInfo("登录成功！")
        return True

    # 抓取单个图片网页并提取text文本  主要是提供给checkURL函数去查找该图片的点赞或者喜爱数
    def getHTML(self, url):
        # 随机选择一个伪装user-agent
        user_agent = random.choice(self.setting.user_agent_list)
        # 获得网页访问语言配置
        language = self.setting.language
        #传递给header
        header = {'User-Agent' : user_agent, 'Accept-Language' : language}
        try:
            r = rq.get(url, headers = header, timeout = self.setting.timeout)  # 连接超时时间设置
            r.raise_for_status()        # 访问失败则抛出异常
            return r.text
        except:
            # 若捕获异常说明图片主页信息访问失败,保存爬虫记录并返回空字符串
            self.setting.logInfo("单张图片信息网页访问异常！可能网络连接已中断！")
            self.saveSetting()
            return ""

    # 访问搜索结果的某一页中并提取出本页所有的图片链接
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
            sys._exit(0)
        # 配置检索本页图片链接的正则表达式格式
        url_form = re.compile(r'https:\\/\\/i.pximg.net\\/c\\/240x240\\/img-master\\/img\\/\d+\\/\d+\\/\d+\\/\d+\\/\d+\\/\d+\\/\d+_p0_master1200.jpg')
        # 根据正则表达式提取出本页所有符合格式的图片链接，列表形式:[url1, url2,]
        url_list = re.findall(url_form, r.text)
        url_list = [re.sub(r'\\', '', url) for url in url_list]
        # 将所有链接加入到爬虫的未访问链接字典,并设置每个链接的值为0
        for url in url_list:
            self.setting.urls_waitting[url] = 0
        # 根据搜索结果的某一页的信息获取检索结果图片总数，并计算出总页数(一页40张)
        self.setting.total_find_pictures = int(re.findall('<span class="count-badge">\d+', r.text)[0].split('>')[-1])
        self.setting.lenpage = ceil(self.setting.total_find_pictures / 40)
        # 总页数不能超过网页允许普通用户查看的总页数(默认设置的1000)
        if self.setting.lenpage > self.setting.max_lenpage:
            self.setting.lenpage = self.setting.max_lenpage
        return url_list

    # 对每一个图片链接进行访问，得到点赞或喜爱数，若符合要求则下载保存
    def checkURL(self, url):
        id = url[65:-18]        # 获得图片id
        refer = self.setting.refer + id         # 获得图片主页地址
        picture_text = self.getHTML(refer)      # 得到图片主页文本
        if not picture_text:                    # 若文本是空的说明网页访问失败
            self.isrunning = False              # 把爬虫运行状态改为False，准备退出爬虫
            self.setting.working_thread -= 1    # 终止该线程
            return
        # 查找该图片的喜爱数或点赞数
        likecount = re.findall(r'"likeCount":\d+', picture_text)
        if likecount:     # 若查找到了喜爱数
            likecount = int(likecount[0].split(':')[-1])
        else:               # 若没有喜爱数信息,则查找点赞数信息代替喜爱数信息
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
        # 若图片喜爱/点赞数小于阈值
        else:
            try:
                self.setting.urls_waitting.pop(url) # 从待处理的图片链接字典中删除该图片
            except:
                pass
        # 若以上流程都未出错,则该线程正常结束,更新数据
        self.setting.working_thread -= 1
        self.setting.finished_thread += 1
        self.setting.total_browsed_pictures += 1

    # 下载保存原始高清图片
    def getPicture(self, url, refer, likecount, id):
        # 以下几行是为了拼接url和refer链接得到高清图片的地址
        user_agent_list = self.setting.user_agent_list
        user_agent = random.choice(user_agent_list)
        figname = self.setting.fig + url[45:-15]
        # 依次尝试访问以jpg, png和gif为后缀的地址
        figurl = figname + '.jpg'
        header = {'User-Agent' : user_agent, 'Referer' : refer}
        try:
            r = self.session.get(figurl, headers = header, timeout = self.setting.timeout)  # 连接超时时间设置
            r.raise_for_status()
        except:
            figurl = figname + '.png'
            try:
                r = self.session.get(figurl, headers = header, timeout = self.setting.timeout)  # 连接超时时间设置
                r.raise_for_status()
            except:
                figurl = figname + '.gif'
                try:
                    r = self.session.get(figurl, headers = header, timeout = self.setting.timeout)  # 连接超时时间设置
                    r.raise_for_status()
                except:
                    # TODO 若以上三种后缀都不对,则可能下载图片过程中S出错,或者是其它后缀,此处可能会出bug
                    self.setting.logInfo("图片下载异常！")
                    # print(refer)
                    self.saveSetting()
                    return False
        # 图片名字为likecount + 图片id + 后缀;  filename = 路径 + 图片名字
        filename = os.path.join(self.setting.result_dir, str(likecount) + '_' + id + figurl[-4:])
        # 在保存一张图片时,用线程锁锁上,防止保存出错
        with self.setting.lock:
            # 保存图片
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
            # 存储运行状态参数(当前页面,总浏览数,总下载数,检索结果页面总数，检索出的图片总数)
            with open(self.setting.pagenum_path, 'w', encoding='utf8') as f:
                f.write(str(self.setting.pagenum) + " " +
                        str(self.setting.total_browsed_pictures) + " " +
                        str(self.setting.total_download) + " " +
                        str(self.setting.lenpage) + " " +
                        str(self.setting.total_find_pictures))
            self.setting.logInfo("当前爬取状态已成功保存!")



    # 对每一页的图片链接列表挨个爬取
    def crawl_url_list(self, url_list):
        length = len(url_list)      # 列表中链接总个数
        for i,url in enumerate(url_list):   # 对列表中每一个链接
            # 以下循环监听爬虫状态 以及 等待分配可用线程
            while(True):
                # 如果爬虫异常终止 并且 所有线程都运行结束
                if not self.isrunning and not self.setting.working_thread:
                    sys.exit(0)     # 退出爬虫并抛出异常
                # 如果爬虫正常运行 并且 存在空闲线程 则退出监听状态
                if self.isrunning and self.setting.working_thread < self.setting.max_thread:
                    break
                # 若程序正常运行  且没有空闲线程  则休眠self.setting.sleep(默认0.5s)时间之后，再次查询
                time.sleep(self.setting.sleep)
            t = threading.Thread(target=self.checkURL, args=(url,))     # 分配线程
            self.setting.working_thread += 1        # 运行中的线程数加1
            t.start()           # 开始运行线程
            # 每启动一个新线程就打印当前的状态信息
            self.setting.logInfo("浏览:%d | 下载:%d | 检索结果:%d || "
                                 "本页进度%2d | %2d || 页面进度:"
                                 "%d | %d || 已完成:%d | 工作中:%d"
                  % (self.setting.total_browsed_pictures,self.setting.total_download,
                     self.setting.total_find_pictures,
                     i+1, length, self.setting.pagenum, self.setting.lenpage,
                     self.setting.finished_thread, self.setting.working_thread))

    # 爬虫主函数
    def run(self):
        # 登录
        if self.login():
            self.isrunning = True   # 若成功，则将爬虫运行状态改为True,表示正常运行
        else:
            sys.exit(0)             # 若不成功，退出爬虫，并抛出异常
        if self.setting.urls_waitting:  # 如果历史记录中有未访问的图片网页，则优先处理这些
            self.crawl_url_list(list(self.setting.urls_waitting.keys()))    # 爬取历史记录中未处理的网页
            self.setting.pagenum += 1            # 本页爬完，准备访问下一页
            self.saveSetting()
        while self.setting.pagenum <= self.setting.lenpage:      # 若爬完所有页面，则终止
            word = "%20".join(self.setting.keyword.split())     # 多个检索关键词用%20拼接
            page_url = self.setting.website + word + self.setting.page + str(self.setting.pagenum)  # 得到检索结果某一页的地址
            # page_url = self.setting.website + self.setting.keyword + self.setting.page + str(pagenum)
            url_list = self.getURL_fromPage(page_url)       # 爬取检索结果的某页，并从页面中提取出所有图片(约39或40个，视频跳过不管)
            self.saveSetting()                  # 每访问一次新的页面后保存记录
            self.crawl_url_list(url_list)       # 爬取该页的所有图片
            self.setting.pagenum += 1                        # 本页爬完，准备访问下一页
        # 爬完所有网页，保存状态并退出
        self.saveSetting()
        sys.exit(0)

# 操作系统调用本程序入口
if __name__ == '__main__':
    # 获得配置
    setting = Setting()
    # 是否初始化
    if setting.cleanDir:  # 若初始化
        setting.clean()  # 执行初始化
    setting.logInfo("开始爬取！搜索关键词为：" + setting.keyword)
    setting.logInfo( "正在尝试第一次登录...")
    # 循环监听
    while(True):
        crawler = MyPixivCrawler()  # 生成爬虫
        try:
            crawler.run()       # 执行爬虫，若登录失败或者运行过程中连接中断会抛出异常
        except: # 捕获异常
            # 若是爬虫运行结束正常退出，则关闭该程序
            if crawler.setting.pagenum > crawler.setting.lenpage:
                setting.logInfo("爬取结束！成功爬取到%d张图片!" % crawler.setting.total_download)
                break
            # 若因为网络连接中断非正常退出则休眠5s再尝试重新登录
            setting.logInfo("正在尝试重新登录...")
            time.sleep(setting.restart_sleep)


