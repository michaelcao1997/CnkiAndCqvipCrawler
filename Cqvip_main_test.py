#!/usr/bin/env python
#-*- coding:utf-8 -*-
# author:hcj
# @File    : Cqvip_main.py
# datetime:2019/6/19 9:43
import queue
import sys
import threading
from urllib.parse import quote
import multiprocessing
from HCJ_py_timer import LoopTimer
import urllib.request
from bs4 import BeautifulSoup
import time
import re
from HCJ_Buff_Control import Read_buff,Write_buff
#构造不同条件的关键词搜索
from HCJ_DB_Helper import HCJ_MySQL
values = {
           '1': 'k', # 标题
           '2': 'w', # 作者
           '3': 'k', # 关键词
           '4': 'o', # 单位
    }

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) Gecko/20100101 Firefox/23.0'}
concurrent = 5 # 采集线程数
conparse = 10 # 解析线程数
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

            if self.is_parse or int(Read_buff(file_buff="Config.ini", settion="Cqvip",info='stopflag'))==0:  # 解析
                try:
                    url,data = self.data_list.get(timeout=3)  # 从数据队列里提取一个数据
                except Exception as e:  # 超时以后进入异常
                    data = None
                # 如果成功拿到数据，则调用解析方法
                if data is not None:
                    self.parse(url,data)  # 调用解析方法
            else:
                break  # 结束while 无限循环

        print('退出%d号解析线程' % self.number)

    # 页面解析函数

    def parse(self,url,_soup):
        _Paper = InitDict()
        deff = _soup.find('span', class_="detailtitle")
        _Paper['url'] = url  # 获得【链接】
        _Paper['title'] = deff.find('h1').text  # 获得【标题】
        str1 = deff.find('strong').text.split('\xa0\xa0')
        _Paper['unit'] = str1[0].split('|')[0]  # 获得【单位】
        _Paper['authors'] = str1[0].split('|')[1]  # 获得【作者】
        _Paper['publication'] = str1[1]  # 获得【出版社】
        deff2 = _soup.select('table', class_="datainfo f14")
        _Paper['abstract'] = deff2[0].text.replace('\n', '').split('：', 1)[1]  # 获得【摘要】
        p = deff2[1].text
        _Paper['type'] = deff2[1].text.split('【分　类】', 1)[1].split('【关键词】')[0].replace('\n', '')  # 获得【分类】
        _Paper['keywords'] = deff2[1].text.split('【关键词】', 1)[1].split('【出　处】')[0].replace('\n', '')  # 获得【关键词】
        StrComeFrom = deff2[1].text.split('【出　处】', 1)[1].split('【收　录】')[0].replace('\n', '')
        Strlist = re.split(r"[;,\s]\s*", StrComeFrom)
        t = 0
        for st in Strlist:
            if st:
                if "年" in st:
                    if '》' in st:
                        _Paper['year'] = st.split('》')[1]  # 获得【出版年份】
                    else:
                        _Paper['year'] = st
                if "共" not in st and "页" in st:
                    _Paper['pagecode'] = st  # 获得【页码】
                if "期" in st:
                    _Paper['issue'] = st  # 获得【期】
        # print(_Paper)
        InsetDbbyDict("`cqvipcrawler`.`result`", _Paper)

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
        while self.req_list.qsize() > 0 or int(Read_buff(file_buff="Config.ini", settion="Cqvip",info='stopflag'))==0:
            # 从请求队列里提取url
            url = self.req_list.get()
            # print('%d号线程采集：%s' % (self.number, url))
            # 防止请求频率过快，随机设置阻塞时间
            time.sleep(0.1)
            # 发起http请求，获取响应内容，追加到数据队列里，等待解析
            response = self.GetSoup(url)
            self.data_list.put([url,response])  # 向数据队列里追加
    def GetSoup(self,url=None):
        req = urllib.request.Request(url=url, headers=headers)
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'lxml')
        return soup
def Up_division_int(A, B):
    '''
     向上整除
    :param A:
    :param B:
    :return:
    '''
    return int((A + B - 1) / B)
class Cqvip_Crawler:
    def __init__(self,db,Input=None,SearchMode=None,StartTime=None,EndTime=None,StartPage=None,SettingPath='./Config.ini'):
        self.db=db
        self.SearchName='Cqvip'  # 万方
        self.SettingPath=SettingPath # 配置文件地址
        self._Perpage=10 # 每页显示20
        self._ResultDbTable='CqvipResult'
        if  Input is None and SearchMode is None:
            self.Input=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='input') # 输入内容
            self.SearchMode=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='searchmode') # 模式选择
            self.StartTime=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='starttime') # 开始年份
            self.EndTime=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='endtime') # 结束年份
            self.StartPage=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='startpage') # 开始页数
            self.MaxPage=Read_buff(file_buff=self.SettingPath,settion=self.SearchName,info='maxpage') # 开始页数
        else:
            # Todo
            pass
    def GetMaxPage(self):
        index_url = "http://www.cqvip.com/data/main/search.aspx?action=so&curpage=1&perpage=%s&%s=%s"%(str(self._Perpage),str(values[self.SearchMode]),quote(str(self.Input)))
        soup = self.GetSoup(url=index_url)
        deff = soup.select('p')[0].text
        summarys = int(deff.split('\r\n')[1].split('"recordcount":')[1].split(',')[0].strip())
        print("查询到共%s相关文献"%summarys)
        self.MaxPage=Up_division_int(summarys,int(self._Perpage))
        Write_buff(file_buff="Config.ini", settion="Cqvip", info="maxpage", state=self.MaxPage)
        return summarys,self.MaxPage
    def GetSoup(self,url=None):
        req = urllib.request.Request(url=url, headers=headers)
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'lxml')
        return soup
    def WriteAllUrlIntoDBMain(self):
        summarys,self.MaxPage = self.GetMaxPage()  # 最大页数
        self.StartPage = Read_buff(file_buff=self.SettingPath, settion=self.SearchName, info='startpage')  # 开始页数
        t=time.time()
        Write_buff(file_buff="Config.ini", settion="Cqvip", info="flag_get_all_url", state=0)
        for i in range(int(self.StartPage),self.MaxPage):
            print("共有%s页，当前为%s页，获得文献链接的进度完成%.2f" % (self.MaxPage, i,(int(i)/int(self.MaxPage))*100))
            Write_buff(file_buff="Config.ini", settion="Cqvip", info="startpage", state=i+1)
            page_url = "http://www.cqvip.com/data/main/search.aspx?action=so&curpage=%s&perpage=20&%s=%s" % (
                str(i), str(values[self.SearchMode]), quote(str(self.Input)))
            threading.Thread(target=self.WriteUrlIntoDB, args=( page_url,i)).start()
            time.sleep(0.5)
        Write_buff(file_buff="Config.ini",settion="Cqvip",info="flag_get_all_url",state=1)
        print(time.time()-t)
    def WriteUrlIntoDB(self,page_url,page):
        soup = self.GetSoup(url=page_url)
        deff = soup.find_all('th')
        for k in range(len(deff)):
            Href = deff[k].a['href']
            if 'http' not in Href or 'www' not in Href:
                Href = deff[k].a['href'].replace('\\', '')
                url = "http://www.cqvip.com/" + quote(Href)
                #_UrlList.append(url)
                sql="INSERT INTO `cqvipcrawler`.`databuff` (`Page`, `PageNum`,`PageIndex`, `Url`) VALUES ('%s', '%s', '%s','%s');\n" % (
                    str(page), str(k), str(page) + '-' + str(k), url)
                row = self.db.insert(sql) # 插入
    def GetDicPaper(self,_soup=None,_url=None):
        _Paper = InitDict()
        deff = _soup.find('span', class_="detailtitle")
        _Paper['url'] = _url  # 获得【链接】
        try:
            _Paper['title'] = deff.find('h1').text  # 获得【标题】
            str1 = deff.find('strong').text.split('\xa0\xa0')
            _Paper['unit'] = str1[0].split('|')[0]  # 获得【单位】
            _Paper['authors'] = str1[0].split('|')[1]  # 获得【作者】
            _Paper['publication'] = str1[1]  # 获得【出版社】
            deff2 = _soup.select('table', class_="datainfo f14")
            _Paper['abstract'] = deff2[0].text.replace('\n', '').split('：', 1)[1]  # 获得【摘要】
            p = deff2[1].text
            _Paper['type'] = deff2[1].text.split('【分　类】', 1)[1].split('【关键词】')[0].replace('\n', '')  # 获得【分类】
            _Paper['keywords'] = deff2[1].text.split('【关键词】', 1)[1].split('【出　处】')[0].replace('\n', '')  # 获得【关键词】
            StrComeFrom = deff2[1].text.split('【出　处】', 1)[1].split('【收　录】')[0].replace('\n', '')
            Strlist = re.split(r"[;,\s]\s*", StrComeFrom)
            t = 0
            for st in Strlist:
                if st:
                    if "年" in st:
                        if '》' in st:
                            _Paper['year'] = st.split('》')[1]  # 获得【出版年份】
                        else:
                            _Paper['year'] = st
                    if "共" not in st and "页" in st:
                        _Paper['pagecode'] = st  # 获得【页码】
                    if "期" in st:
                        _Paper['issue'] = st  # 获得【期】
        except:
            print("解析链接出现错误")
        return _Paper
    def GetUrlFromDb(self,num=20):
        sql="select `PageIndex`,`Url` from `databuff` where `State`in (0,-10) ORDER BY `Page` ASC, `PageNum` limit %s "%num
        _rows=self.db.do_sql(sql)
        if _rows:
            if len(_rows)>0:
                _UrlList=[x[1] for x in _rows]
                for i in [x[0] for x in _rows]:
                    self.db.upda_sql("update `databuff` set `State`=10 where `PageIndex`='%s'"%i)
                return _UrlList
        else:
            return ""
    def CqvipMain(self):

        LoopTimer(0.1, self.GetPaperResultFromUrl).start()
    def GetPaperResultFromUrl(self):
        '''
        通过GetUrlFromDb获得20个链接，然后进行爬取，爬取后写入数据库
        :return:
        '''
        UrlList = self.GetUrlFromDb(num=20)  # 获取20个
        threading.Thread(target=self.ThreadGetAndWrite, args=(UrlList,)).start()

    def ThreadGetAndWrite(self,UrlList):
        print("线程开始")
        if   len(UrlList)>0:
            startTime = time.time()
            for i in range(len(UrlList)):
                try:
                    soup = self.GetSoup(url=UrlList[i])
                    Paper = self.GetDicPaper(_soup=soup, _url=UrlList[i])
                    InsetDbbyDict("`cqvipcrawler`.`result`", Paper)
                except:
                    print("失败")
                    pass
            print("成功插入%s,耗时%s"%(len(UrlList),(time.time() - startTime)))
            time.sleep(0.05)
        else:
            pass
def InitDict():
    dir = {'url' :'', 'title' :'','authors':'','unit' :'','publication' :'','keywords' :'','abstract' :'','year' :'','volume' :'','issue' :'','pagecode' :'','doi' :'','string' :'','sponser' :'','type' :''}
    return dir

def InsetDbbyDict(table,Dict):
    COLstr = ''  # 列的字段
    ROWstr = ''  # 行字段
    for key in Dict.keys():
        COLstr = COLstr + ' ' + '`' + key + '`,'

        ROWstr = (ROWstr + '"%s"' + ',') % (str(Dict[key]).replace('%',">").replace('\n','').replace('\"',"#"))
    sql = "INSERT INTO %s (%s) VALUES (%s);\n" % (
        table,COLstr[:-1], ROWstr[:-1])
    sql_update="Update `databuff` set `State`=20 where `Url`='%s' "%str(Dict['url']).replace('\n','')


    result_dic=db.insert(sql)
    if  result_dic['result']:
        db.upda_sql(sql_update)
    else:
        print(result_dic['err'])
        db.upda_sql("Update `databuff` set `State`=-10 where `Url`='%s' "%str(Dict['url']).replace('\n',''))


class PaperAll(object):
    pass

def CreatResultDBTable(TableName):
    '''
    创建结构数据库表单，如果不存在就创建
    :return:
    '''
    str = ""
    Dict=InitDict()
    for key in Dict.keys():
        str+="`%s` varchar(200) DEFAULT NULL,"%key
    CreatDBTableSql='\
        CREATE TABLE IF NOT EXISTS `%s` (\
          `id` int(11) unsigned NOT NULL AUTO_INCREMENT,\
          `url` varchar(200) DEFAULT NULL, \
          `title` varchar(200) DEFAULT NULL,\
          `authors` varchar(200) DEFAULT NULL,\
          `unit` varchar(200) DEFAULT NULL,\
          `publication` varchar(200) DEFAULT NULL,\
          `keywords` varchar(200) DEFAULT NULL,\
          `abstract` varchar(200) DEFAULT NULL,\
          `year` varchar(200) DEFAULT NULL,\
          `volume` varchar(200) DEFAULT NULL,\
          `issue` varchar(200) DEFAULT NULL,\
          `pagecode` varchar(200) DEFAULT NULL,\
          `doi` varchar(200) DEFAULT NULL,\
          `string` varchar(200) DEFAULT NULL,\
          `sponser` varchar(200) DEFAULT NULL,\
          `type` varchar(200) DEFAULT NULL,\
          PRIMARY KEY (`id`)\
        ) ENGINE=InnoDB DEFAULT CHARSET=latin1; '%TableName
    dict_result= db.upda_sql(CreatDBTableSql)
    if  not dict_result:
        print("创建出现问题")
class ClockProcess(multiprocessing.Process):
    def __init__(self, interval):
        multiprocessing.Process.__init__(self)
        self.interval = interval

    def run(self):
        _db=HCJ_MySQL()
        _Cqvip = Cqvip_Crawler(db=_db)
        _Cqvip.WriteAllUrlIntoDBMain()
        print("结束")

def PutUrlToList(Cqvip,num):
    UrlList=Cqvip.GetUrlFromDb(num=num)
    if UrlList:
        if len(UrlList)>0:
            for url in UrlList:
                req_list.put(url)
    else:pass
def ShowStatePro():
    sql_count_all="select count(*) from `databuff` where 1"
    num_all=int(db.do_sql_one(sql_count_all)[0])
    sql_count_done="select count(*) from `databuff` where `State`=20"
    num_done = int(db.do_sql_one(sql_count_done)[0])
    if num_all ==0:
        num_all=1
    if int(Read_buff(file_buff="Config.ini", settion="Cqvip", info='flag_get_all_url')) == 1 and num_all == num_done:
        # 完成全部
        Write_buff(file_buff="Config.ini",settion="Cqvip",info="stopflag",state=1)
        print("#############################################目前有%s条数据，其中已处理的有%s，处理完成度为%.2f##############################" % (num_all, num_done, (int(num_done) / int(num_all)) * 100))
        print("爬取结束")
        sys.exit()
    print("#############################################目前有%s条数据，其中已处理的有%s，处理完成度为%.2f##############################"%(num_all,num_done,(int(num_done)/int(num_all))*100))
if __name__ == '__main__':
    db = HCJ_MySQL()
    Cqvip = Cqvip_Crawler(db=db)
    # 生成请求队列
    req_list = queue.Queue()
    # 生成数据队列 ，请求以后，响应内容放到数据队列里
    data_list = queue.Queue()
    ClockProcess(1).start()
    PutUrlToList(Cqvip,20)
    LoopTimer(0.5, PutUrlToList,args=(Cqvip,20,)).start()
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
