#!/usr/bin/env python3
#-*- coding:utf-8 -*-

# author:hcj
# @File    : Wanfang_main.py
# datetime:2019/6/26 11:40
import queue
import sys
import threading

from urllib.error import URLError, HTTPError
import math
from urllib.parse import quote
import multiprocessing
import requests
from HCJ_py_timer import LoopTimer
import urllib.request
from bs4 import BeautifulSoup
import time
import random
import re
from HCJ_Buff_Control import Read_buff,Write_buff
# 构造不同条件的关键词搜索
from HCJ_DB_Helper import HCJ_MySQL
values = {
           '1': 'k',  # 标题
           '2': 'w',  # 作者
           '3': 'k',  # 关键词
           '4': 'o',  # 单位
    }
SearchDBName = 'Wanfang'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) Gecko/20100101 Firefox/23.0'}
concurrent = 5 # 采集线程数
conparse = 10 # 解析线程数
# 生成请求队列
req_list = queue.Queue()
# 生成数据队列 ，请求以后，响应内容放到数据队列里
data_list = queue.Queue()

class Parse(threading.Thread):
    # 初始化属性
    def __init__(self, number, data_list, req_thread):
        super(Parse, self).__init__()
        self.number = number  # 线程编号
        self.data_list = data_list  # 数据队列
        self.req_thread = req_thread  # 请求队列，为了判断采集线程存活状态
        self.is_parse = True  # 判断是否从数据队列里提取数据

    def run(self):
        print('启动%d号解析线程' % self.number)
        # 无限循环，
        while True:
            # 如何判断解析线程的结束条件
            for t in self.req_thread:  # 循环所有采集线程
                if t.is_alive():  # 判断线程是否存活
                    break
            else:  # 如果循环完毕，没有执行break语句，则进入else
                if self.data_list.qsize() == 0:  # 判断数据队列是否为空
                    self.is_parse = False  # 设置解析为False
            # 判断是否继续解析

            if self.is_parse or int(Read_buff(file_buff="Config.ini", settion="Wanfang", info='stopflag'))==0:  # 解析

                try:
                    url, data = self.data_list.get(timeout=3)  # 从数据队列里提取一个数据
                except Exception as e:  # 超时以后进入异常
                    data = None
                # 如果成功拿到数据，则调用解析方法
                if data is not None and Wanfang.running:
                    Paper = Wanfang.GetFurtherPaper(url, data)
            else:
                break  # 结束while 无限循环

        print('退出%d号解析线程' % self.number)


class Crawl(threading.Thread): #采集线程类
    # 初始化
    def __init__(self, number, req_list, data_list):
        # 调用Thread 父类方法
        super(Crawl, self).__init__()
        # 初始化子类属性
        self.number = number
        self.req_list = req_list
        self.data_list = data_list
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.89 Safari/537.36'
        }
    # 线程启动的时候调用

    def run(self):
        # 输出启动线程信息
        print('启动采集线程%d号' % self.number)
        # 如果请求队列不为空，则无限循环，从请求队列里拿请求url
        while self.req_list.qsize() > 0 or int(Read_buff(file_buff="Config.ini", settion="Wanfang",info='stopflag'))==0:
            # 从请求队列里提取url
            url = self.req_list.get()
            # print('%d号线程采集：%s' % (self.number, url))
            # 防止请求频率过快，随机设置阻塞时间
            time.sleep(random.randint(5,6))
            # 发起http请求，获取响应内容，追加到数据队列里，等待解析
            response = Wanfang.VisitHtml(url)
            self.data_list.put([url, response])  # 向数据队列里追加


def InitDict():
    dir = {'url': '', 'title' :'','authors':'','unit' :'','publication' :'','keywords' :'','abstract' :'','year' :'','volume' :'','issue' :'','pagecode' :'','doi' :'','string' :'','sponser' :'','type' :''}
    return dir

def InsetDbbyDict(table, Dict):
    sql = "INSERT INTO %s (`url`, `title`, `authors`, `unit`, `publication`, `keywords`, `abstract`, `year`, `volume`, " \
          "`issue`, `pagecode`, `doi`, `sponser`, `type`, `source`) VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', " \
          "'%s', '%s', '%s', '%s', '%s', '%s', '%s');\n" % \
          (table, Dict['url'], Dict['title'], Dict['authors'], Dict['unit'], Dict['publication'], Dict['keywords'],
           Dict['abstract'], Dict['year'], Dict['volume'], Dict['issue'], Dict['pagecode'], Dict['doi'], Dict['sponser'],
           Dict['type'], SearchDBName)

    sql_update = "Update `databuff` set `State`=20 where `Url`='%s' " % Dict['url']
    result_dic = db.insert(sql)
    if result_dic['result']:
        db.upda_sql(sql_update)
    else:
        print(result_dic['err'])
        db.upda_sql("Update `databuff` set `State`=-10 where `Url`='%s' " % Dict['url'])


class ClockProcess(multiprocessing.Process):  # multiprocessing.Process产生的时子进程
    def __init__(self, interval):
        multiprocessing.Process.__init__(self)
        self.interval = interval

    def run(self):  # 在调用子进程的start() 的时候，默认会执行run() 方法
        _db = HCJ_MySQL()
        _Wanfang = WanFangCrawler(db=_db)
        _Wanfang.GetAllUrl()
        print("采集链接结束")


def ShowStatePro():
    sql_count_all = "select count(*) from `databuff` where 1"
    num_all = int(db.do_sql_one(sql_count_all)[0])
    sql_count_done = "select count(*) from `databuff` where `State`=20"
    num_done = int(db.do_sql_one(sql_count_done)[0])
    sql_count_done_not_in_year = "select count(*) from `databuff` where `State`=-5"
    num_done_not_in_year = int(db.do_sql_one(sql_count_done_not_in_year)[0])
    num_done_not_in_year = num_done_not_in_year if num_done_not_in_year > 0 else 0
    num_done = num_done + num_done_not_in_year
    if num_all == 0:
        num_all = 1
    print(
        "#############################################目前有%s条数据，其中已处理的有%s，其中年份不符合的有%s,处理完成度为%.2f,##############################" % (
            num_all, num_done, num_done_not_in_year, (int(num_done) / int(num_all)) * 100))
    if int(Read_buff(file_buff="Config.ini", settion="Wanfang", info='flag_get_all_url')) == 1 and num_all == num_done:
        # 完成全部
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="stopflag", state=1)
        print("爬取结束")
        sys.exit()


class WanFangCrawler:

    def __init__(self,db,Input=None,SearchMode=None,StartTime=None,EndTime=None,StartPage=None,SettingPath='./Config.ini'):
        self.db = db
        self.SearchName = 'Wanfang'  # 万方
        self.SettingPath = SettingPath # 配置文件地址
        self._Perpage = 50  # 每页显示50
        self._ResultDbTable='WanFangResult'
        self.running = False  # 标记程序是否正常运行
        self.further_url = list()
        if Input is None and SearchMode is None:
            self.Input=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='input') # 输入内容
            self.SearchMode=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='searchmode') # 模式选择
            self.StartTime=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='starttime') # 开始年份
            self.EndTime=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='endtime') # 结束年份
            self.StartPage=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='startpage') # 开始页数
            self.MaxPage=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='maxpage') # 开始页数
        else:
            # Todo
            pass

    def GetBaseUrl(self):
        if self.SearchMode == '1':
            search_mode = '题名'
        elif self.SearchMode == '2':
            search_mode = '作者'
        elif self.SearchMode == '3':
            search_mode = '关键词'
        else:
            search_mode = '作者单位'
        index_url1 = 'http://g.wanfangdata.com.cn/search/searchList.do?searchType=all&pageSize=50&searchWord='  # pageSize=20每页记录限制为50条
        index_url2 = '&showType=detail&isHit=null&isHitUnit=&firstAuthor=false&rangeParame=all&navSearchType='
        index_url = index_url1 + '(' + search_mode + ':' + self.Input + ') 起始年:' + self.StartTime + ' 结束年:' + self.EndTime + index_url2  # 搜索时加上时间限制
        return index_url

    def GetMaxPage(self):
        total_record_num = 0
        index_url = self.GetBaseUrl()

        response = self.VisitHtml(url=index_url)
        if self.running:
            html = BeautifulSoup(response.text, "html.parser")  # 获取HTML代码
            total_record_text = html.find('div', class_='left_sidebar_border')
            for item in total_record_text:
                if '条结果' in item:
                    total_record_num = re.findall(r"\d+\.?\d*", item)
                    if str.isdigit(total_record_num[0]):
                        total_record_num = int(total_record_num[0])
                        break
            print("查询到共%s相关文献" % total_record_num)
            page_count = int(math.ceil(total_record_num / self._Perpage))  # 总页数
            self.MaxPage = page_count
            # if page_count > self.MaxPage:  # 当页码非常大的时候，对页码进行限制
            #     page_count = self.MaxPage
            Write_buff(file_buff="Config.ini", settion="Wanfang", info="maxpage", state=self.MaxPage)
            return total_record_num, page_count, index_url

    def VisitHtml(self, url):
        """
        请求访问网页
        :param url: 访问网页的URL
        :return: 请求结果对象
        """
        # IP = ['http://139.199.38.177:8333', 'http://114.249.107.250:8570', 'http://222.85.28.130:8107', 'http://114.245.186.249:8106',
        #       'http://212.64.51.13:8665', 'http://40.73.36.247:8644', 'http://218.60.8.99:8282', 'http://39.137.69.10:8760',
        #       'http://211.101.154.105:9064', 'http://27.191.234.69:8252']
        # proxy_ip = random.choice(IP)
        # proxies = {'http': proxy_ip}  # proxy ip pool

        attempts = 0
        success = False
        while attempts < 20 and not success:
            try:
                response = requests.get(url, timeout=4)  # 获取网页HTML的URL编码数据
                success = True
                self.running = True
            except HTTPError or URLError:
                attempts += 1
                print("第" + str(attempts) + "次重试！！")
                if attempts == 20:
                    self.running = False
                    return False
            except requests.exceptions.ReadTimeout:
                print("请求连接超时")
            else:
                return response

    def GetAllUrl(self):

        total_record_num, self.MaxPage, index_url = self.GetMaxPage()  # 最大页数
        self.StartPage = Read_buff(file_buff=self.SettingPath, settion=self.SearchName, info='startpage')  # 开始页数
        t = time.time()
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="flag_get_all_url", state=0)
        for i in range(int(self.StartPage), self.MaxPage + 1):
            print("共有%s页，当前为%s页，获得文献链接的进度完成%.2f" % (self.MaxPage, i, (int(i) / int(self.MaxPage)) * 100))
            Write_buff(file_buff="Config.ini", settion="Wanfang", info="startpage", state=i + 1)
            url_list=self.GetFurtherUrl(i, index_url)
            # print(url_list)
            threading.Thread(target=self.WriteUrlIntoDB, args=(url_list,)).start()
            time.sleep(0.5)
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="flag_get_all_url", state=1)
        print(time.time() - t)

    def GetFurtherUrl(self, page_num, index_url):
        """
        获取详细网页的URL
        :param page_num:
        :param base_url:
        :return:
        """
        url_list = []
        index_url = index_url + '&page=' + str(page_num)  # 翻页
        # print(index_url)
        response = self.VisitHtml(index_url)
        if self.running:
            bs = BeautifulSoup(response.text, "html.parser")
            info_url = bs.find_all('i', class_='icon icon_Miner')
            for item in info_url:
                onclick = item.attrs['onclick']
                _id = onclick.split(',')[1].strip("\\'")
                _type = onclick.split(',')[2].lstrip("\\'").rstrip("\\')")
                further_url = 'http://g.wanfangdata.com.cn/details/detail.do?_type=' + _type + '&id=' + _id
                url_list.append(further_url)
            return url_list

    def WriteUrlIntoDB(self, url):
        for i in url:
            sql = "INSERT INTO `databuff` (`Url`, `source`) VALUES ('%s', '%s')" % (i, SearchDBName)
            row = self.db.insert(sql)
            if not row['result']:
                print(row)



    def GetFurtherPaper(self, _url, _soup):
        _Paper = InitDict()
        all_author = ''
        if self.running:
            html = BeautifulSoup(_soup.text, "html.parser")  # 获取HTML代码
            try:
                title = html.find('font', {'style': 'font-weight:bold;'})
                title = title.get_text()
            except:
                print('您的IP访问过于频繁，请输入验证码后继续使用')
            else:
                abstract = html.find('div', class_='abstract')
                if abstract:
                    abstract = abstract.text.split('摘要')[0].replace('\n', '')
                    _Paper['abstract'] = abstract.replace("'", "")
                literature_type = html.find('div', class_='crumbs')
                if '期刊' in literature_type.text:
                    literature_type = 'J'
                    author_item = html.find_all('input', class_='dw')
                    for auth in author_item:
                        author = auth.attrs['value']
                        all_author = all_author + author + ";"
                    all_author = all_author.rstrip(';')
                elif '学位' in literature_type.text:
                    literature_type = 'D'
                    author_item = html.find('a', id='card01')
                    all_author = author_item.get_text()
                elif '会议' in literature_type.text:
                    literature_type = 'C'
                    author_item = html.find_all('a', class_='info_right_name')
                    for auth in author_item:
                        all_author = all_author + auth.get_text() + ';'
                    all_author = all_author.rstrip(';')
                elif '标准' in literature_type.text:
                    literature_type = 'S'
                elif '科技报告' in literature_type.text:
                    literature_type = 'R'
                elif '专利' in literature_type.text:
                    literature_type = 'P'
                else:
                    literature_type = "Z"  # 未定义类型文献
                info = html.find_all('div', class_='info_right')

                _Paper['authors'] = all_author
                for item in info:
                    screen = item.parent.text
                    if 'doi：' in screen:
                        doi = item.get_text()
                        _Paper['doi'] = doi
                    if '关键词：' in screen:
                        keywords = item.get_text().rstrip('\n').lstrip('\n\n').replace('\n\n', ';')
                        _Paper['keywords'] = keywords
                    if '作者单位' in screen and ('Author' not in screen):
                        unit = item.get_text().strip('\n').replace('\n', ';')
                        _Paper['unit'] = unit
                    if '学位授予单位' in screen:
                        _Paper['unit'] = item.get_text().strip('\n')
                        _Paper['publication'] = item.get_text().strip('\n')
                    if '会议名称' in screen:
                        _Paper['publication'] = item.get_text().strip('\n')
                    if '年，卷(期)：' in screen and ('作者单位' not in screen):
                        year_volume_date = item.get_text().strip('\n')
                        year = year_volume_date.split(',')[0]  # 出版年份
                        volume = year_volume_date.split(',')[1].split('(')[0]  # 卷
                        date = get_string_start_end(item.get_text(), '(', ')')  # 期
                        _Paper['year'] = year
                        _Paper['volume'] = volume
                        _Paper['issue'] = date
                    if '在线出版日期' in screen:
                        _Paper['year'] = item.get_text().replace('\r\n', '').replace('\t', '').strip().split('年')[0]
                    if '学位年度' in screen:
                        _Paper['year'] = item.get_text()
                    if '基金项目：' in screen and ('作者单位' not in screen):
                        sponser = item.get_text().strip('\n').replace('\n', ';')  # 基金项目
                        _Paper['sponser'] = sponser
                    if '页数：' in screen and ('作者单位' not in screen):
                        page_num = item.get_text()  # 页数
                    if '页码：' in screen and ('作者单位' not in screen):
                        page_number = item.get_text()  # 页码
                        _Paper['pagecode'] = page_number
                    if '刊名：' in screen and ('作者单位' not in screen):
                        publication = item.get_text().strip('\n')  # 刊名
                        _Paper['publication'] = publication
                _Paper['title'] = title
                _Paper['url'] = _url
                _Paper['abstract'] = abstract.replace("'", "")
                _Paper['type'] = literature_type
            print(_Paper)
            InsetDbbyDict("`crawler`.`result`", _Paper)
        # print(_Paper)
        return _Paper

    def GetUrlFromDb(self, num=20):
        sql = "SELECT `Source`,`Url` from `databuff` where `State`in (0,-10) limit %s " % num  # 一次读20条URL用于爬取数据
        _rows = self.db.do_sql(sql)
        if _rows:
            if len(_rows)>0:
                _UrlList=[x[1] for x in _rows]
                for i in _UrlList:
                    self.db.upda_sql("update `databuff` set `State`=10 where `Url`='%s'" % i)
                return _UrlList
        else:
            return ""


def get_string_start_end(string, start, end):
    """
    获取字符串中，两个字符之间的字符
    :param string:字符串
    :param start: 开始字符
    :param end: 结束字符
    :return: start-end之间字符
    """
    start_index = string.find(start)
    end_index = string.find(end)
    return string[start_index + 1:end_index]


def PutUrlToList(Wanfang, num):
    UrlList = Wanfang.GetUrlFromDb(num=num)
    if UrlList:
        if len(UrlList) > 0:
            for url in UrlList:
                req_list.put(url)  # 将从数据库获得的20条数据放入queue
    else:
        pass


def CreatUrlBuffTable(TableName):
    CreatDBTableSql = '\
            CREATE TABLE IF NOT EXISTS `%s` (\
            `Index` int(11) unsigned NOT NULL AUTO_INCREMENT,\
            `Url` VARCHAR(255) DEFAULT NULL,\
            `State` INT(11) NULL DEFAULT \'0\'  COMMENT \'-5 日期不对 -10 出现错误 0 初始 10 处理中 20 处理结束\',\
            `Datetime` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,\
            `Source` VARCHAR(200) NULL DEFAULT NULL,\
            UNIQUE INDEX `Url` (`Url`),\
            PRIMARY KEY (`Index`)\
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8; ' % TableName
    dict_result = db.upda_sql(CreatDBTableSql)
    if not dict_result:
        print("创建%s表出现问题" % TableName)

def CreatResultDBTable(TableName):
    '''
    创建结构数据库表单，如果不存在就创建
    :return:
    '''
    CreatDBTableSql = '\
        CREATE TABLE IF NOT EXISTS `%s` (\
          `id` int(11) unsigned NOT NULL AUTO_INCREMENT,\
          `url` varchar(255) DEFAULT NULL, \
          `title` varchar(200) DEFAULT NULL,\
          `authors` varchar(200) DEFAULT NULL,\
          `unit` text DEFAULT NULL,\
          `publication` varchar(200) DEFAULT NULL,\
          `keywords` varchar(200) DEFAULT NULL,\
          `abstract` text DEFAULT NULL,\
          `year` varchar(200) DEFAULT NULL,\
          `volume` varchar(200) DEFAULT NULL,\
          `issue` varchar(200) DEFAULT NULL,\
          `pagecode` varchar(200) DEFAULT NULL,\
          `doi` varchar(200) DEFAULT NULL,\
          `sponser` text DEFAULT NULL,\
          `type` varchar(200) DEFAULT NULL,\
          `source` VARCHAR(200) NULL DEFAULT NULL,\
          PRIMARY KEY (`id`)\
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8; ' % TableName
    dict_result = db.upda_sql(CreatDBTableSql)
    if not dict_result:
        print("创建%s表出现问题" % TableName)


def main():
    ClockProcess(1).start()  # 开始多线程，时间间隔为1秒
    PutUrlToList(Wanfang, 20)  # 往队列queue放20条数据，
    LoopTimer(0.5, PutUrlToList, args=(Wanfang, 20,)).start()
    LoopTimer(1, ShowStatePro).start()
    # 生成N个采集线程
    req_thread = []
    for i in range(concurrent):
        t = Crawl(i + 1, req_list, data_list)  # 创造线程
        t.start()
        req_thread.append(t)
    # 生成N个解析线程
    parse_thread = []
    for i in range(conparse):
        t = Parse(i + 1, data_list, req_thread)  # 创造解析线程
        t.start()
        parse_thread.append(t)
    for t in req_thread:
        t.join()
    for t in parse_thread:
        t.join()


def init_main():
    if int(Read_buff(file_buff="Config.ini", settion="Wanfang", info='restart')) == 1:
        CreatResultDBTable("result")
        CreatUrlBuffTable("databuff")
        db.do_sql("TRUNCATE `databuff`;")  # 清空databuff表
        db.do_sql("TRUNCATE `result`;")  # 清空result表
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="restart", state=0)
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="startpage", state=1)
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="stopflag", state=0)
        Write_buff(file_buff="Config.ini", settion="Wanfang", info="flag_get_all_url", state=0)



if __name__ == '__main__':
    multiprocessing.freeze_support()  # 在Windows下运行有可能崩溃(开启了一大堆新窗口、进程)，可以通过freeze_support()来解决
    db = HCJ_MySQL()
    Wanfang = WanFangCrawler(db=db)
    init_main()
    main()

