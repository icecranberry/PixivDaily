import os
import threading
import datetime
import shutil
# 配置参数
class Setting(object):
    def __init__(self):
        ######################### 以下参数可以修改 #################################
        # 此处输入搜索关键词
        self.keyword = ''
        # 下边引号中输入p站登录邮箱
        self.pixiv_id = ''
        # 下边输入p站密码
        self.password =  ''
        # 此处设置是否打印每张图片的点赞/喜爱数 打印改为True
        self.likecount_visible = False
        # 此处设置点赞或者喜爱数下限
        self.low = 200
        # 最大线程总数量,控制同时访问网页的个数,根据网络状况设定
        self.max_thread = 2
        # 线程数量刷新间隔,单位为s,检测是否有空闲的线程
        self.sleep = 0.5
        # 初始化文件夹,改为True将清除当前路径下除了本文件的其他所有文件，慎用
        self.cleanDir = False
        # 程序出现异常后重新尝试登陆的间隔时间,单位s
        self.restart_sleep = 5
        # p站允许普通用户显示的检索结果最大页数
        self.max_lenpage = 1000
        ########################### 以下参数不要更改###########################################
        self.website = 'https://www.pixiv.net/search.php?s_mode=s_tag&word='
        self.page = '&order=date_d&p='
        self.refer = 'https://www.pixiv.net/member_illust.php?mode=medium&illust_id='
        self.fig = 'https://i.pximg.net/img-original/img/'
        self.total_find_pictures = 0     # 检索出来的图片总数
        self.lenpage = 1000              # 存储检索结果总页数，会实时更新
        self.user_agent_list = [
             'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/45.0.2454.85 Safari/537.36 115Browser/6.0.3',
             'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; en-us) AppleWebKit/534.50 (KHTML, like Gecko) Version/5.1 Safari/534.50',
             'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-us) AppleWebKit/534.50 (KHTML, like Gecko) Version/5.1 Safari/534.50',
             'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.0; Trident/4.0)',
             'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)',
             'Opera/9.80 (Windows NT 6.1; U; en) Presto/2.8.131 Version/11.11',
             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_0) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.56 Safari/535.11',
             'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; Trident/4.0; SE 2.X MetaSr 1.0; SE 2.X MetaSr 1.0; .NET CLR 2.0.50727; SE 2.X MetaSr 1.0)',
             'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0',
             'Mozilla/5.0 (Windows NT 6.1; rv:2.0.1) Gecko/20100101 Firefox/4.0.1',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36'
            ]       # 网页访问来源伪装为浏览器(列表中随机选择一个)
        self.language = 'zh-CN,zh;q=0.9,en;q=0.8'   # 网页语言
        self.timeout = 60       # 访问超时时间
        self.pagenum = 1        # 当前页数,默认从第一页开始，可以从历史状态恢复
        self.TempData_dir = 'TempData'   # 历史记录文件夹
        self.result_dir = 'pictures'      # 爬取的图片文件夹
        # 存储历史页码和图片总数
        self.pagenum_path = os.path.join(self.TempData_dir, 'pagenum.txt')
        # 存储图片信息
        self.picture_dic = {}
        self.pic_dic_path = os.path.join(self.TempData_dir, 'picture_dic.json')
        # 存储当前页未访问的图片链接
        self.urls_waitting = {}
        self.urls_waitting_path = os.path.join(self.TempData_dir, 'urls_waitting.json')

        self.log_path = 'log.txt'           # 存储日志信息
        self.working_thread = 0             # 工作中的线程个数
        self.finished_thread = 0            # 本次工作已经完成浏览及鉴定的图片数
        self.lock = threading.RLock()       # 线程锁
        self.total_browsed_pictures = 0     # 历史浏览及鉴定过的图片总数
        self.total_download = 0             # 历史下载的图片总数

        # 登录
        self.login_path = 'https://accounts.pixiv.net/login'
        self.post_login_path = 'https://accounts.pixiv.net/api/login?lang=zh'
        self.check_login_path = 'https://www.pixiv.net/setting_user.php'
        # 若文件夹不存在，则创建文件夹
        if not os.path.isdir(self.TempData_dir):
            os.makedirs(self.TempData_dir)
        if not os.path.isdir(self.result_dir):
            os.makedirs(self.result_dir)

    # 初始化文件夹的函数
    def clean(self):
        if os.path.isfile(self.log_path):
            os.remove(self.log_path)
        if os.path.isdir(self.result_dir):
            shutil.rmtree(self.result_dir)
        if os.path.isdir(self.TempData_dir):
            shutil.rmtree(self.TempData_dir)
        if os.path.isdir('__pycache__'):
            shutil.rmtree('__pycache__')
        self.logInfo("已成功初始化文件夹!")

    # 打印日志信息并保存
    def logInfo(self, string):
        time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')    # 当前日期
        string = time + "\t" + string
        # 写入日志文件中
        with open(self.log_path, 'a', encoding='utf8') as f:
            f.write(string + '\n')
        print(string)
