#!/usr/bin/env python
# -*- coding:utf-8 -*-
# author:hcj
# @File    : Cqvip_main.py
# datetime:2019/6/19 9:43
import argparse
import queue
import random
import sys
import threading
from urllib.parse import quote
import multiprocessing
from HCJ_py_timer import LoopTimer
import urllib.request
from bs4 import BeautifulSoup
import time
import re
from HCJ_Buff_Control import Read_buff, Write_buff
# 构造不同条件的关键词搜索
from HCJ_DB_Helper import HCJ_MySQL
from PublicDef import *
SearchDBName="Cqvip"
values = {
    '1': 'k',  # 标题
    '2': 'w',  # 作者
    '3': 'k',  # 关键词
    '4': 'o',  # 单位
    '5': 'mn',  # 刊名
}

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) Gecko/20100101 Firefox/23.0'}
concurrent=int(Read_buff(file_buff="./Config.ini",settion='Setting',info='Cqvip_CollectNum').replace(' ',''))
conparse=int(Read_buff(file_buff="./Config.ini",settion='Setting',info='Cqvip_parsenum').replace(' ',''))
interval=int(Read_buff(file_buff="./Config.ini",settion='Setting',info='Cqvip_interval').replace(' ',''))
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

            if self.is_parse or '0' in (Read_buff(file_buff="Config.ini", settion=SearchDBName, info='stopflag')):  # 解析
                try:
                    url, data = self.data_list.get(timeout=3)  # 从数据队列里提取一个数据
                except Exception as e:  # 超时以后进入异常
                    data = None
                # 如果成功拿到数据，则调用解析方法
                if data is not None:
                    parse(url, data)  # 调用解析方法
            else:
                break  # 结束while 无限循环

        print('退出%d号解析线程' % self.number)
    # 页面解析函数

class Crawl(threading.Thread):  # 采集线程类
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
        while self.req_list.qsize() > 0 or '0' in (
                Read_buff(file_buff="Config.ini", settion=SearchDBName, info='stopflag')):
            # 从请求队列里提取url
            url = self.req_list.get()
            # print('%d号线程采集：%s' % (self.number, url))
            # 防止请求频率过快，随机设置阻塞时间
            time.sleep(random.randint(interval*10, (interval+2)*10)/10)
            # 发起http请求，获取响应内容，追加到数据队列里，等待解析
            response = GetSoup(url)
            self.data_list.put([url, response])  # 向数据队列里追加

def Up_division_int(A, B):
    '''
     向上整除
    :param A:
    :param B:
    :return:
    '''
    return int((A + B - 1) / B)

class Cqvip_Crawler:
    def __init__(self, db, Input=None, SearchMode=None, StartTime=None, EndTime=None, StartPage=None,
                 SettingPath='./Config.ini'):
        self.db = db
        self.SearchName = SearchDBName  # 万方
        self.SettingPath = SettingPath  # 配置文件地址
        self._Perpage = 10  # 每页显示20
        self._ResultDbTable = 'CqvipResult'
        if Input is None and SearchMode is None:
            self.StartTime = Read_buff(file_buff=self.SettingPath, settion=self.SearchName, info='starttime')  # 开始年份
            self.EndTime = Read_buff(file_buff=self.SettingPath, settion=self.SearchName, info='endtime')  # 结束年份
            self.StartPage = Read_buff(file_buff=self.SettingPath, settion=self.SearchName, info='startpage')  # 开始页数
            self.title = Read_buff(file_buff=self.SettingPath, settion=SearchDBName, info='title')
            self.authors = Read_buff(file_buff=self.SettingPath, settion=SearchDBName, info='authors')
            self.keywords = Read_buff(file_buff=self.SettingPath, settion=SearchDBName, info='keywords')
            self.unit = Read_buff(file_buff=self.SettingPath, settion=SearchDBName, info='unit')
            self.BaseKeyword = ""
            if RemoveSpecialCharacter(self.title) != "":
                self.BaseKeyword = self.BaseKeyword + "&k=" + quote(self.title)
            if RemoveSpecialCharacter(self.authors) != "":
                self.BaseKeyword = self.BaseKeyword + "&w=" + quote(self.authors)
            if RemoveSpecialCharacter(self.keywords) != "":
                self.BaseKeyword = self.BaseKeyword + "&k=" + quote(self.keywords)
            if RemoveSpecialCharacter(self.unit) != "":
                self.BaseKeyword = self.BaseKeyword + "&o=" + quote(self.unit)

        else:
            # Todo
            pass

    def GetMaxPage(self):
        index_url = "http://www.cqvip.com/data/main/search.aspx?action=so&curpage=1&perpage=%s&%s" % (
            str(self._Perpage), self.BaseKeyword)
        soup = GetSoup(url=index_url)
        deff = soup.select('p')[0].text
        summarys = int(deff.split('\r\n')[1].split('"recordcount":')[1].split(',')[0].strip())
        print("查询到共%s相关文献" % summarys)
        self.MaxPage = Up_division_int(summarys, int(self._Perpage))
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="maxpage", state=self.MaxPage)
        return summarys, self.MaxPage



    def WriteAllUrlIntoDBMain(self):
        summarys, self.MaxPage = self.GetMaxPage()  # 最大页数
        self.StartPage = Read_buff(file_buff=self.SettingPath, settion=self.SearchName, info='startpage')  # 开始页数
        t = time.time()
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="flag_get_all_url", state=0)
        for i in range(int(self.StartPage), self.MaxPage):
            print("%s采集器，共有%s页，当前为%s页，获得文献链接的进度完成%.2f" % (SearchDBName,self.MaxPage, i, (int(i) / int(self.MaxPage)) * 100))
            Write_buff(file_buff="Config.ini", settion=SearchDBName, info="startpage", state=i + 1)
            page_url = "http://www.cqvip.com/data/main/search.aspx?action=so&curpage=%s&perpage=20&%s" % (
                str(i), self.BaseKeyword)
            threading.Thread(target=self.WriteUrlIntoDB, args=(page_url, i)).start()
            time.sleep(0.5)
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="flag_get_all_url", state=1)
        print(time.time() - t)

    def WriteUrlIntoDB(self, page_url, page):
        soup = GetSoup(url=page_url)
        if soup:
            deff = soup.find_all('th')
            for k in range(len(deff)):
                Href = deff[k].a['href']
                if 'http' not in Href or 'www' not in Href:
                    Href = deff[k].a['href'].replace('\\', '')
                    url = "http://www.cqvip.com/" + quote(Href)
                    # _UrlList.append(url)
                    sql = "INSERT INTO `crawler`.`%s` ( `Url`,`Source`) VALUES ('%s','%s');" % (DbDatabuff,url,SearchDBName)

                    row = self.db.insert(sql)  # 插入


    def GetUrlFromDb(self, num=20):
        sql = "select `Index`,`Url` from `%s` where `State`in (0,-10) and `Source`='%s' limit %s " % (DbDatabuff,SearchDBName,num)
        _rows = self.db.do_sql(sql)
        if _rows:
            if len(_rows) > 0:
                _UrlList = [x[1] for x in _rows]
                for i in [x[0] for x in _rows]:
                    self.db.upda_sql("update `%s` set `State`=10 where `Index`='%s'" % (DbDatabuff,i))
                return _UrlList
        else:
            return ""

def InitDict():
    dir = {'url': '', 'title': '', 'authors': '', 'unit': '', 'publication': '', 'keywords': '', 'abstract': '',
           'year': '', 'volume': '', 'issue': '', 'pagecode': '', 'doi': '', 'sponser': '', 'type': ''}
    return dir


def GetSoup(url=None):
    try:
        req = urllib.request.Request(url=url, headers=headers)
        request = urllib.request.urlopen(req, timeout=8)
        html = request.read()
        soup = BeautifulSoup(html, 'lxml')
    except Exception as e:
        db.upda_sql("update `%s` set `State`=-15 where `Url`='%s'"%(DbDatabuff,url))
        print("Cqvip：无效链接", str(e), url)
        soup=False
    return soup


def parse( url, _soup):
    if _soup is not None:
        _Paper = InitDict()
        _Paper['url'] = url  # 获得【链接】
        try:
            deff = _soup.find('span', class_="detailtitle")
            _Paper['title'] = deff.find('h1').text  # 获得【标题】
            str1 = deff.find('strong').text.split('\xa0\xa0')
            _Paper['publication'] = re.search(r'《(.*)》', str1[0].split('|')[0]).group()  # 获得【单位】
            _Paper['authors'] = str1[0].split('|')[1]  # 获得【作者】
            _Paper['unit'] = str1[1]  # 获得【出版社】
            deff2 = _soup.select('table', class_="datainfo f14")
            _Paper['abstract'] = deff2[0].text.replace('\n', '').split('：', 1)[1].split('：')[1]  # 获得【摘要】
            p = deff2[1].text
            # _Paper['type'] = deff2[1].text.split('【分　类】', 1)[1].split('【关键词】')[0].replace('\n', '')  # 获得【分类】
            _Paper['keywords'] = deff2[1].text.split('【关键词】', 1)[1].split('【出　处】')[0].replace('\n', '')  # 获得【关键词】
            StrComeFrom = deff2[1].text.split('【出　处】', 1)[1].split('【收　录】')[0].replace('\n', '')
            StrComeFrom = changeChineseNumToArab(StrComeFrom)
            Strlist = re.split(r"[;,\s]\s*", StrComeFrom)
            t = 0
            for st in Strlist:
                if st:
                    if "年" in st:
                        if '》' in st:
                            _Paper['year'] = st.split('》')[1]  # 获得【日期】只要数字
                        else:
                            _Paper['year'] = st
                        _Paper['year'] = re.search(r'\d+', _Paper['year']).group()
                    if "共" not in st and "页" in st:
                        _Paper['pagecode'] = st.split('页')[0] if '页' in st else st  # 获得【页码】
                    if "期" in st:
                        _Paper['issue'] = re.search(r'\d+', st).group()  # 获得【期】
            try:
                InsetDbbyDict("`crawler`.`%s`" % Dbresult, _Paper, db,DbDatabuff,Dbresult)
            except:
                print(_Paper['url'], "插入失败")

        except:
            db.upda_sql("update `%s` set `State`=-15 where `Url`='%s'" % (DbDatabuff,_Paper['url']))
            print(_Paper['url'],"goup解析出现错误")
        # print(_Paper)



class ClockProcess(multiprocessing.Process):
    def __init__(self, Crawler):
        multiprocessing.Process.__init__(self)
        self.Crawler = Crawler

    def run(self):
        _db = HCJ_MySQL()
        _Cqvip = self.Crawler(db=_db)
        _Cqvip.WriteAllUrlIntoDBMain()
        print("结束")


def PutUrlToList(Cqvip, num):
    UrlList = Cqvip.GetUrlFromDb(num=num)
    if UrlList:
        if len(UrlList) > 0:
            for url in UrlList:
                req_list.put(url)
    else:
        pass

def main():
    ClockProcess(Cqvip_Crawler).start()
    PutUrlToList(Cqvip, 20)
    LoopTimer(0.5, PutUrlToList, args=(Cqvip, 20,)).start()
    LoopTimer(1, ShowStatePro,args=(db,SearchDBName,DbDatabuff,Dbresult,)).start()
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
    if '1' in str(Read_buff(file_buff="Config.ini", settion=SearchDBName, info='restart')):
        CreatResultDBTable(db,Dbresult)
        CreatUrlBuffTable(db,DbDatabuff)
        time.sleep(0.05)
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="restart", state=0)
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="startpage", state=1)
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="stopflag", state=0)
        Write_buff(file_buff="Config.ini", settion=SearchDBName, info="flag_get_all_url", state=0)
    if '0' in str(Read_buff(file_buff="Config.ini", settion=SearchDBName, info='restart')):
        db.upda_sql("Update `%s` set `State`=0 where `State`=10"%DbDatabuff)
    time.sleep(1)

ex_dbname = Read_buff(file_buff="Config.ini", settion=SearchDBName, info='ex_dbname')
DbDatabuff="databuff"+str(ex_dbname)
Dbresult="result"+str(ex_dbname)
def ProcessMain():
    global db,Cqvip
    db = HCJ_MySQL()
    Cqvip = Cqvip_Crawler(db=db)
    multiprocessing.freeze_support()  # 多进程打包的话必须加上
    init_main()
    if '0' in (Read_buff(file_buff="Config.ini", settion=SearchDBName, info='stopflag')) :
        main()
if __name__ == '__main__':
   # ProcessMain()
   db = HCJ_MySQL()
   Cqvip = Cqvip_Crawler(db=db)
   url="http://www.cqvip.com/%22/QK/93419A/200901/29132001.html%22"
   g=GetSoup(url)
   parse(url,g)