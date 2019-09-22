import os
from datetime import datetime as date
from datetime import timedelta as delta
from enum import Enum
from time import time

import numpy as np
import pandas as pd
from columnar import columnar

import Functions as f


# BACKTEST
class Account():
    
    def __init__(self):
        self.balance = 1
        self.max = 0
        self.min = 1
        self.listtxns = list()

    def getBalance(self):
        if self.balance < 0.01:
            self.balance = 0.01
        # balance = self.balance if not self.balance < 0.01 else 0.01
        return self.balance

    def reset(self, balance=1):
        self.balance = balance

    def modify(self, xbt, timestamp):
        txn = Txn()
        txn.amount = xbt
        txn.timestamp = timestamp
        txn.acctbalance = self.balance
        txn.percentchange = round((xbt / self.balance), 3)

        self.listtxns.append(txn)
        self.balance = self.balance + xbt
        if self.balance > self.max: self.max = self.balance
        if self.balance < self.min: self.min = self.balance    

    def getPeriodNum(self, timestamp, period='month'):
        timestamp = f.checkDate(timestamp)
        with f.Switch(period) as case:
            if case('month'):
                return timestamp.month
            elif case('week'):
                return timestamp.strftime("%V")

    def getPercentChange(self, balance, change):
        return f.percent(change / balance)

    def printSummary(self, period='month'):
        data = []
        headers = ['Period', 'AcctBalance', 'Change', 'PercentChange']

        periodnum = self.getPeriodNum(self.listtxns[0].timestamp, period)
        prevTxn = None
        prevBalance = 1
        change = 0.0

        for t in self.listtxns:     
            if self.getPeriodNum(t.timestamp, period) != periodnum:
                if prevTxn is None: prevTxn = t
                data.append([
                    periodnum,
                    '{:.{prec}f}'.format(t.acctbalance, prec=3),
                    round(change, 3),
                    self.getPercentChange(prevBalance, change)
                ])
                prevTxn = t
                prevBalance = t.acctbalance
                change = 0
                periodnum = self.getPeriodNum(t.timestamp, period)
            
            change = change + t.amount

        table = columnar(data, headers, no_borders=True, justify='r')
        print(table)

    def printtxns(self):
        data = []
        headers = ['Date', 'AcctBalance', 'Amount', 'PercentChange']
        for t in self.listtxns:
            data.append([
                '{:%Y-%m-%d %H}'.format(t.timestamp),
                '{:.{prec}f}'.format(t.acctbalance, prec=3),
                '{:.{prec}f}'.format(t.amount, prec=2),
                f.percent(t.percentchange)
            ])
        table = columnar(data, headers, no_borders=True, justify='r')
        print(table)

    def getDf(self):
        df = pd.DataFrame(columns=['CloseTime', 'Balance', 'PercentChange'])
        for i, t in enumerate(self.listtxns):
            df.loc[i] = [t.timestamp, t.acctbalance, t.percentchange]
        return df

class Backtest():
    def __init__(self, symbol, startdate, strats=[],
    stratactive=False, daterange=365, df=None, row=None, write=False, account=None):
        
        if account == None:
            self.account = Account()

        self.i = 1
        self.candles = []
        self.write = write
        
        # get rid of some of this during optimization tests probably
        # dfsym = (pd.read_csv('../JambotFunctionApp/symbols.csv')
        #             .rename(columns=str.lower))
        # dfsym = dfsym.loc[dfsym.symbol==symbol]
        if row is None:
            dfsym = pd.read_csv(os.path.join(f.currentdir(), 'symbols.csv'))
            dfsym = dfsym[dfsym['symbol']==symbol]
            row = list(dfsym.itertuples())[0]

        self.row = row
        self.symbolshort = row.symbolshort
        self.urlshort = row.urlshort
        self.symbolbitmex = row.symbolbitmex
        self.altstatus = bool(row.altstatus)
        self.decimalfigs = row.decimalfigs

        self.symbol = symbol
        self.startdate = f.checkDate(startdate)
        self.stratactive = stratactive
        self.strats = strats
        self.tradingenabled = True
        
        if df is None:
            self.df = f.getDataFrame(symbol=symbol, startdate=f.startvalue(startdate), enddate=f.enddate(startdate, daterange))
        else:
            self.df = df
                    
        # add blank cols
        c = dict()
        c['BalanceBTC'] = 0.000
        self.df = self.df.assign(**c)
        
        self.startrow = self.df.loc[self.df['CloseTime'] == pd.Timestamp(self.startdate)].index[0]

        self.loadcols()

        for strat in self.strats:
            strat.init(sym=self)

        # print('startdate: ' + str(self.startdate))
        # print('startrow: ' + str(self.startrow))
        # print(len(self.df))

    def initCandle(self, row):
        self.curcandle = row
        # self.curcandle = Candle()
        # c = self.curcandle
        # c.timestamp = row.CloseTime
        # c.open = row.Open
        # c.high = row.High
        # c.low = row.Low
        # c.close = row.Close
        # c.ema200 = row.ema200
        # c.ema50 = row.ema50
        # c.i = row.name
        self.candles.append(self.curcandle)

    def loadcols(self):
        self.colHigh = self.df.columns.get_loc('High')
        self.colLow = self.df.columns.get_loc('Low')
        self.colBalanceBTC = self.df.columns.get_loc('BalanceBTC')

    def decidefull(self):
        length = len(self.df)
        for row in self.df.itertuples():
            self.initCandle(row)
            
            self.i = row.Index
            i = self.i
            if not i < self.startrow:
                if i == length: return

                for strat in self.strats:
                    strat.decide(row)

                if self.write: self.writerow(i)

    def writerow(self, i):
        df = self.df
        
        if not self.stratactive:
            df.iat[i, self.colBalanceBTC] = self.account.getBalance()

            for strat in self.strats:
                strat.writerow(i)

    def printfinal(self, strat=0):
        a = self.account
        strat = self.strats[0]
        data = []
        headers = ['Symbol', 'Min', 'Max', 'Final', 'Goodtrades']

        data.append([
            self.symbol,
            round(a.min, 3),
            round(a.max, 3),
            round(a.balance, 3),
            '{}/{}/{}'.format(strat.goodtrades(), strat.tradecount(), strat.unfilledtrades)])

        table = columnar(data, headers, no_borders=True, justify='r')
        print(table)

    def writecsv(self):
        self.df.to_csv('dfout.csv')
        self.account.getDf().to_csv('df2out.csv')

    def expectedOrders(self):
        # don't use this yet.. maybe when we have combined strats?
        
        expected = []
        for strat in self.strats:
            for order in strat.finalOrders():
                expected.append(order)
        
        return expected


# STRAT
class Strategy():
    def __init__(self, name, weight=1, lev=5):
        self.name = name
        self.i = 1
        self.status = 0
        self.weight = weight
        self.entryprice = 0
        self.exitprice = 0
        self.maxspread = 0.1
        self.slippage = 0.0044
        self.lev = lev
        
        self.trades = []
        self.trade = None
        self.sym = None    
            
    def loadcols(self):
        df = self.sym.df
        self.colStatus = df.columns.get_loc(self.name + '_Status')
        self.colContracts = df.columns.get_loc(self.name + '_Contracts')
        self.colInfo = df.columns.get_loc(self.name + '_Info')
        self.colPnl = df.columns.get_loc(self.name + '_Pnl')

    def tradecount(self):
        return len(self.trades)

    def lasttrade(self):
        return self.trades[self.tradecount() - 1]

    def getTrade(self, i):
        numtrades = self.tradecount()
        if i > numtrades: i = numtrades
        return self.trades[i - 1]

    def goodtrades(self):
        count = 0
        for t in self.trades:
            if t.isgood():
                count += 1
        return count

    def getSide(self):
        status = self.status
        if status == 0:
            return 0
        elif status < 0:
            return - 1
        elif status > 0:
            return 1

    def writerow(self, i):
        df = self.sym.df
        if not self.trade is None:
            df.iat[i, self.colStatus] = self.status
            df.iat[i, self.colContracts] = self.trade.contracts
            df.iat[i, self.colPnl] = self.trade.pnlcurrent()

    def checkfinalorders(self, finalorders):
        for i, order in enumerate(finalorders):
            if order.contracts == 0:
                del finalorders[i]
        return finalorders

    def printtrades(self, maxmin=0, maxlines=-1):
        data = []
        headers = ['N', 'Timestamp', 'Sts', 'Dur', 'Entry', 'Exit', 'Contracts', 'conf', 'Pnl', 'Bal']
        for i, t in enumerate(self.trades):
            if not maxmin == 0 and maxmin * t.pnlfinal <= 0: continue
            
            data.append([
                t.tradenum,
                '{:%Y-%m-%d %H}'.format(t.candles[0].CloseTime),
                t.status,
                t.duration(),
                '{:,.0f}'.format(t.entryprice),
                '{:,.0f}'.format(t.exitprice),
                '{:,}'.format(t.filledcontracts),
                round(t.conf, 3),
                '{:.2%}'.format(t.pnlfinal),
                round(t.exitbalance, 2)
            ])
        
            if i == maxlines: break

        table = columnar(data, headers, no_borders=True, justify='r', min_column_width=2)
        print(table)

class Strat_TrendRev(Strategy):
    # variable slippage % based on emavty or smavty
    # try variable stopout % too?
    # if orders haven't filled after n candles (3 ish?), close only, or close and enter?
    # count unfilled trades

    def __init__(self, speed=(8,8), weight=1, norm=(1,4), lev=5):
        self.name = 'trendrev'
        super().__init__(self.name, weight, lev)
        self.stoppercent = -0.04
        self.slippage = 0.004
        self.speed = speed
        self.norm = norm
        self.lasthigh, self.lastlow = 0, 0
        self.unfilledtrades = 0

    def init(self, sym):
        self.sym = sym
        self.a = self.sym.account
        sym.df = f.setTradePrices(self.name, sym.df, speed=self.speed)
        sym.df = f.setVolatility(sym.df, norm=self.norm)

    def exittrade(self):
        # need to check limitclose and stop orders before closing trade.
        # May need to manually fill at current candle close price.
        trade = self.trade
        c = self.candle
        # CANT fill a close if buy isn't filled!!!!

        if not trade.stopped and trade.limitopen.filled and not trade.limitclose.filled:
            trade.stop.cancel()
            trade.limitclose.fill(c=c, price=c.Close)
            self.unfilledtrades += 1
            
        self.trade.exittrade()

    def inittrade(self, side, entryprice, balance=None, temp=False):
        if balance is None:
            balance = self.sym.account.getBalance()

        contracts = f.getContracts(balance, self.lev, entryprice, side, self.sym.altstatus) * self.weight

        c = self.candle
        if side * c.trend == 1:
            conf = 1.5 - abs(c.conf) * 2
        else:
            conf = 0.5 + abs(c.conf) * 2
        
        trade = Trade_TrendRev()
        trade.init(price=entryprice, targetcontracts=contracts, strat=self, conf=conf, side=side, temp=temp)
        
        return trade
    
    def entertrade(self, side, entryprice):
        self.trade = self.inittrade(side=side, entryprice=entryprice)
        self.trade.checkorders(self.sym.curcandle)
        
    def decide(self, c):
        self.candle = c
        self.i = c.Index
        pxhigh, pxlow = c.trendrev_high, c.trendrev_low

        # if we exit a trade and limitclose isnt filled, limitopen may wait and fill in next candles, but current trade gets 0 profit. Need to exit properly.

        # Exit Trade
        if not self.trade is None:
            self.trade.checkorders(c)

            if self.trade.side == 1:
                if c.High > pxhigh and c.High > self.lasthigh:
                    self.exittrade()
            else:
                if c.Low < pxlow and c.Low < self.lastlow:
                    self.exittrade()

            if not self.trade.active:
                self.trade = None
        
        # Enter Trade
        if self.trade is None:
            if c.High > pxhigh:
                self.entertrade(-1, pxhigh)
            elif c.Low < pxlow:
                self.entertrade(1, pxlow)

        self.lasthigh, self.lastlow = pxhigh, pxlow

    def finalOrders(self, u, weight):
        lstorders = []
        balance = u.totalbalancewallet * weight
        curr_cont = u.getPosition(self.sym.symbolbitmex)['currentQty']
        c = self.candle
        symbol = self.sym.symbolbitmex
        
        # maybe set threshold for adjusting order size based on conf
        # Cant have market buy in bulk order...!
        
        # Get Close and Stop from current trade
        t_current = self.trade

        t_current.rescaleorders(balance=balance)
        t_current.stop.contracts = 0

        # CLOSE
        # Check if current limitclose is still open with same side
        prevclose = self.trades[-2].limitclose
        if prevclose.marketfilled:
            prevclose_actual = u.getOrderByKey(key=f.key(symbol, 'limitclose', prevclose.side, 3))
            if not prevclose_actual is None and prevclose_actual['side'] == prevclose.side:
                prevclose.setname('marketclose')
                prevclose.ordtype2 = 'Market'
                prevclose.execInst = 'Close'
                lstorders.append(prevclose)
            
        # May need to check this every 5 mins or something
        if not curr_cont == 0:
            t_current.limitclose.contracts = curr_cont * -1
            lstorders.append(t_current.limitclose)

        # BUY
        currentbuy = t_current.limitopen
        currentbuy_actual = u.getOrderByKey(key=f.key(symbol, 'limitopen', currentbuy.side, 1))
        if currentbuy.filled:
            if currentbuy.marketfilled and curr_cont == 0 and t_current.duration() == 4:
                currentbuy.setname('marketbuy') # need a diff name cause 2 limitbuys possible
                currentbuy.ordtype2 = 'Market'
                lstorders.append(currentbuy)
                t_current.stop.contracts += currentbuy.contracts * -1

            # Init next trade to get limitopen
            px = c.trendrev_high if t_current.side == 1 else c.trendrev_low
            t_next = self.inittrade(side=t_current.side * -1, entryprice=px, balance=balance, temp=True)
            lstorders.append(t_next.limitopen)
            lstorders.append(t_next.stop)
        else:
            # Only till max 4 candles into trade
            lstorders.append(currentbuy)
            # t_current.stop.contracts += currentbuy.contracts * -1

        # STOP
        # if curr_cont == 0 AND we have a limit order open!
        # stop depends on either a position OR a limitopen
        # stop wont be added till next hour once it already exists.. fix.
        if not t_current.stop.filled:
            t_current.stop.contracts += curr_cont * -1
            # print(t_current.stop.contracts)
            
            if not currentbuy_actual['orderQty'] is None:
                t_current.stop.contracts += currentbuy_actual['orderQty'] * -1
                # print(t_current.stop.contracts)

            lstorders.append(t_current.stop)
        else:
            # should check to make sure position is closed?
            pass
            

        return self.checkfinalorders(lstorders)

class Strat_Trend(Strategy):
    def __init__(self, speed=(18,18), mr=False, weight=1, lev=5, opposite=False):
        self.name = 'trend'
        super().__init__(self.name, weight, lev)
        self.meanrevenabled = mr
        self.emaactive = False
        self.meanrev = False
        self.meanrevnext = False
        self.meanrevmin = 0.05
        self.stoppercent = -0.04
        self.speed = speed
        self.opposite = opposite
        self.modiopp = 1 if not opposite else -1
        # self.againstspeed = speed[0]
        # self.withspeed = speed[1]

    def init(self, sym):
        self.sym = sym
        if self.sym.altstatus == True:
            self.lev = 2.5
            
        c = dict()
        c[self.name + '_Status'] = np.nan
        c[self.name + '_Contracts'] = np.nan
        c[self.name + '_Info'] = np.nan
        c[self.name + '_Pnl'] = 0.00
        sym.df = sym.df.assign(**c)

        self.loadcols()

        sym.df = f.setTradePrices(self.name, sym.df, speed=self.speed)

    def getRecentWinConf(self):
        recentwin = False
        closedtrades = self.tradecount()
        ctOffset = closedtrades - 1 if closedtrades < 3 else 2
        for y in range(closedtrades, closedtrades - ctOffset - 1, -1):
            if self.getTrade(y).pnlfinal > 0.05:
                recentwin = True
        
        recentwinconf = 0.25 if recentwin else 1
        return recentwinconf

    def getConfidence(self, bypassmeanrev=False):
        winConfActive = True

        if (self.meanrev or self.meanrevnext) and not bypassmeanrev:
            return 1.5

        # midpoint = self.maxspread / 2
        c = self.candle
        emaspread = abs(c.emaspread) #??? why abs??

        tempconfidence = round(1.5 - f.emaExp(x=emaspread, c=f.getC(self.maxspread)), 3)

        recentwinconf = self.getRecentWinConf()
        confidence = recentwinconf if recentwinconf <= 0.5 and winConfActive else tempconfidence
        return confidence

    def enterTrade(self, side, entryprice): 
        
        self.status = side
        if self.meanrev: self.status *= 2 

        confidence = self.getConfidence() if self.emaactive else 1
        
        modi = 1 if not self.meanrev else -1
        self.entryprice = entryprice * (1 + self.slippage * self.getSide() * modi * self.modiopp)
        
        if not self.sym.stratactive:
            if self.sym.write: # probs don't need this at all anymore
                self.sym.df.iloc[self.i, self.colInfo] = 'Entry: {}  conf: {}'.format(round(self.entryprice, 3), confidence)

            contracts = int(f.getContracts(self.sym.account.getBalance(), self.lev, self.entryprice, self.getSide(), self.sym.altstatus) * confidence * self.weight)
        
        if self.trade is None:
            self.trade = Trade_Trend()

        self.trade.init(self.entryprice, contracts, self, confidence)

    def exitTrade(self, exitprice):
        
        modi = 1 if not self.meanrev else -1
        modiopp = self.modiopp

        if not self.sym.stratactive:
            self.trade.exitprice = exitprice # can't get this till trade.exitprice is set
            minpnl = self.trade.pnlmaxmin(-1)
            if minpnl < self.stoppercent and (self.meanrev or self.opposite): # stopped out!
                exitprice = f.getPrice(self.stoppercent, self.entryprice, self.getSide())
                modiopp = 1

        exitprice = exitprice * (1 + self.getSide() * self.slippage * -1 * modi * modiopp)
        if not self.trade is None:
            self.trade.exit(exitprice)

        # set meanrev back on or off
        if self.meanrev:
            self.meanrev = False
        elif self.meanrevenabled and self.trade.pnlcurrent(self.sym.curcandle) > self.meanrevmin:
            self.meanrev = True

        self.trade = None

    def decide(self, c):
        if not self.trade is None: self.trade.addCandle(c)
        
        self.i = c.Index
        opp = self.modiopp
        highenter = c.trend_high
        lowenter = c.trend_low
        
        highexit = highenter
        lowexit = lowenter

        self.Highexit = highexit
        self.Lowexit = lowexit

        # Main classifier
        with f.Switch(self.status * opp) as case:
            if case(1, -2):
                if c.Low < lowexit:
                    self.exitTrade(lowexit)
                elif not self.trade is None and abs(self.status) == 2:
                    if self.trade.isstopped():
                        self.exitTrade(self.trade.stoppx)
                
                if self.meanrev == False: #short enter check
                    if c.Low < lowenter:
                        self.enterTrade(-1 * opp, lowenter)
                elif self.meanrev == True:
                    if c.Low < lowexit:
                        self.enterTrade(1, lowexit)

            elif case(-1, 2):
                if c.High > highexit:
                    self.exitTrade(highexit)
                elif not self.trade is None and abs(self.status) == 2:
                    if self.trade.isstopped():
                        self.exitTrade(self.trade.stoppx)

                if self.meanrev == False: #long enter check
                    if c.High > highenter:
                        self.enterTrade(1 * opp, highenter)
                elif self.meanrev == True:
                    if c.High > highexit:
                        self.enterTrade(-1, highexit)
                
            elif case(0):
                if c.High > highenter:
                    self.enterTrade(1 * opp, highenter)
                elif c.Low < lowenter:
                    self.enterTrade(-1 * opp, lowenter)

    def finalOrders(self, u, weight):
        # should actually pass something at the 'position' level, not user?
        lstOrders = []
        c = self.sym.curcandle
        side = self.getSide()
        price = c.trend_low if self.status == 1 else c.trend_high
        
        # stopclose
        lstOrders.append(Order(
                    price = price,
                    side = -1 * side,
                    contracts = -1 * u.getPosition(self.sym.symbolbitmex)['currentQty'],
                    symbol = self.sym.symbolbitmex,
                    name = 'stopclose',
                    ordtype = 'Stop',
                    sym=self.sym))

        # stopbuy
        contracts = f.getContracts(
                        u.totalbalancewallet * weight,
                        self.lev,
                        price,
                        -1 * side,
                        self.sym.altstatus)

        lstOrders.append(Order(
                    price = price,
                    side = -1 * side,
                    contracts = contracts,
                    symbol = self.sym.symbolbitmex,
                    name = 'stopbuy',
                    ordtype = 'Stop',
                    sym=self.sym))

        return self.checkfinalorders(lstOrders)

    def printtrades(self, maxmin=0, maxlines=-1):
        data = []
        headers = ['Num', 'Timestamp', 'Status', 'EntryPrice', 'ExitPrice', 'Contracts', 'Conf', 'Pnl', 'bal']
        for i, t in enumerate(self.trades):
            if not maxmin == 0 and maxmin * t.pnlfinal <= 0: continue

            data.append([
                t.tradenum,
                '{:%Y-%m-%d %H}'.format(t.candles[0].CloseTime),
                t.status,
                '{:,.0f}'.format(t.entryprice),
                '{:,.0f}'.format(t.exitprice),
                '{:,}'.format(t.contracts),
                '{:.{prec}f}'.format(t.confidence, prec=2),
                '{:.2%}'.format(t.pnlfinal),
                round(t.exitbalance, 2)
            ])
            
            if i == maxlines: break

        table = columnar(data, headers, no_borders=True, justify='r', min_column_width=2)
        print(table)
        
class Strat_Chop(Strategy):
    def __init__(self, speed=(36,36), weight=1, norm=(1,4), speedtp=(36, 36)):
        self.name = 'chop'
        super().__init__(self.name, weight=weight)
        self.speed = speed
        self.speedtp = speedtp
        self.norm = norm
        # anchordist > 0 - 0.02, step 0.002
        # Order/Stop spread, 

    def init(self, sym):
        self.sym = sym

        # c = dict()
        # c[self.name + '_Status'] = np.nan
        # c[self.name + '_Contracts'] = np.nan
        # c[self.name + '_Info'] = np.nan
        # c[self.name + '_Pnl'] = 0.00
        # sym.df = sym.df.assign(**c)

        # self.loadcols()

        # self.speed = (sym.row.lowernormal, sym.row.uppernormal)

        sym.df = f.setTradePrices(self.name, sym.df, speed=self.speed)
        sym.df = f.setTradePrices('tp', sym.df, speed=self.speedtp)
        sym.df = f.setVolatility(sym.df, norm=self.norm)

    def decide(self, c):
        self.candle = c

        if abs(self.status) == 1:
            self.trade.checkorders(c)
            if not self.trade.active:
                self.trade.exit()
                self.trade = None
        else:
            if c.High >= c.chop_high:
                self.status = -1
                self.entertrade(c.chop_high)
            elif c.Low <= c.chop_low:
                self.status = 1
                self.entertrade(c.chop_low)

    def inittrade(self, entryprice, side, balance=None):
        if balance is None:
            balance = self.sym.account.getBalance()

        contracts = f.getContracts(balance * self.weight, self.lev, entryprice, side, self.sym.altstatus)

        trade = Trade_Chop()
        trade.init(entryprice, contracts, self, side=side)
        return trade
    
    def entertrade(self, entryprice):
        self.trade = self.inittrade(entryprice, self.status)
        self.trade.checkorders(self.candle)

    def getAnchorPrice(self, anchorstart, norm, side):
        return anchorstart * (1 + norm * 0.005 * side * -1)

    def getNextOrdArrays(self, anchorprice, c, side, trade=None):

        orders = OrdArray(
                        ordtype=1,
                        anchorprice=anchorprice,
                        orderspread=0.002 * c.norm,
                        trade=trade,
                        activate=True)
        
        stops = OrdArray(
                        ordtype=2,
                        anchorprice=f.getPrice(
                            -0.01 * c.norm,
                            orders.maxprice,
                            side),
                        orderspread=0.002 * c.norm,
                        trade=trade,
                        activate=False)
        
        outerprice = c.tp_high if side == 1 else c.tp_low

        takeprofits = OrdArray(
                        ordtype=3,
                        anchorprice=trade.anchorstart,
                        outerprice=outerprice,
                        orderspread=0,
                        trade=trade,
                        activate=False)
                        
        # takeprofits = OrdArray(
        #                 3,
        #                 f.getPrice(
        #                     0.02 * c.normtp,
        #                     anchorprice,
        #                     side),
        #                 0.0025 * c.normtp,
        #                 trade,
        #                 False)

        return [orders, stops, takeprofits]

    def finalOrders(self, u, weight):
        lstOrders = []
        balance = u.totalbalancewallet * weight
        remainingcontracts = u.getPosition(self.sym.symbolbitmex)['currentQty']
        # print(remainingcontracts)

        if not self.trade is None:
            # we should be in a trade
            t = self.trade

            # rescale contracts to reflect actual user balance
            targetcontracts = f.getContracts(balance, self.lev, t.anchorstart, t.side, self.sym.altstatus)
            # print(targetcontracts)
            # t.printallorders()

            lstOrders.extend(t.orders.getUnfilledOrders(targetcontracts))
            lstOrders.extend(t.stops.getUnfilledOrders(targetcontracts, remainingcontracts))
            lstOrders.extend(t.takeprofits.getUnfilledOrders(targetcontracts, remainingcontracts))
            
        else:
            # not in a trade, need upper and lower order/stop arrays
            c = self.candle

            trade_long = self.inittrade(c.chop_low, 1, balance=balance)
            lstOrders.extend(trade_long.orders.orders)
            lstOrders.extend(trade_long.stops.orders)

            trade_short = self.inittrade(c.chop_high, -1, balance=balance)
            lstOrders.extend(trade_short.orders.orders)
            lstOrders.extend(trade_short.stops.orders)

        return self.checkfinalorders(lstOrders)

    def printtrades(self, maxmin=0, maxlines=-1):
        data = []
        headers = ['N', 'Timestamp', 'Sts', 'Dur', 'Anchor', 'Entry', 'Exit', 'Contracts', 'Filled', 'Pnl', 'Balance']
        for i, t in enumerate(self.trades):
            if not maxmin == 0 and maxmin * t.pnlfinal <= 0: continue

            data.append([
                t.tradenum,
                '{:%Y-%m-%d %H}'.format(t.candles[0].CloseTime),
                t.status,
                t.duration(),
                '{:,.0f}'.format(t.anchorstart),
                '{:,.0f}'.format(t.entryprice),
                '{:,.0f}'.format(t.exitprice),
                '({:,} / {:,})'.format(t.filledcontracts, t.targetcontracts),
                t.allfilled(),
                '{:.2%}'.format(t.pnlfinal),
                round(t.exitbalance, 2)
            ])
        
            if i == maxlines: break

        table = columnar(data, headers, no_borders=True, justify='r', min_column_width=2)
        print(table)


# TRADE
class Trade():
    def __init__(self):
        self.candles = []
        self.orders = []
        self.active = True
        self.filledcontracts = 0    
        self.contracts = 0
        self.entryprice = 0
        self.exitprice = 0
        self.pnlfinal = 0
        self.iType = 1
        self.sym = None
        self.strat = None
        self.exitbalance = 0
        self.exitcontracts = 0

    def init(self, price, targetcontracts, strat, conf=1, entryrow=0, side=None, temp=False):
        self.entrytarget = price
        self.entryprice = 0
        self.targetcontracts = int(targetcontracts)
        self.strat = strat
        self.sym = self.strat.sym
        self.conf = round(conf, 3)
        self.tradenum = self.strat.tradecount()
        self.candle = self.sym.curcandle
        
        if side is None:
            self.status = self.strat.status
            self.side = self.strat.getSide() # sketch
        else:
            self.status = side
            self.side = side

        self.enter(temp=temp)

    def exittrade(self):
        self.strat.status = 0
        self.pnlfinal = f.getPnl(self.side, self.entryprice, self.exitprice)
        self.exitbalance = self.sym.account.getBalance()
        self.active = False

    def closeorder(self, price, contracts):
        
        if contracts == 0: return

        self.exitprice = (self.exitprice * self.exitcontracts + price * contracts) / (self.exitcontracts + contracts)

        if self.entryprice == 0:
            raise ValueError('entry price cant be 0!')

        self.sym.account.modify(f.getPnlXBT(contracts * -1, self.entryprice, price, self.sym.altstatus), self.candle.CloseTime)
        
        self.exitcontracts += contracts
        self.contracts += contracts

    def closeposition(self):
        closeprice = self.sym.curcandle.Open
        self.closeorder(price=closeprice, contracts=self.contracts * -1)
        self.deactivateorders(closeall=True)

    def getCandle(self, i):
        return self.candles[i - 1]

    def addCandle(self, candle):
        self.candles.append(candle)
        self.candle = candle
    
    def duration(self):
        return len(self.candles)

    def pnlcurrent(self, candle=None):
        if candle is None: candle = self.getCandle(self.duration())
        return f.getPnl(self.side, self.entryprice, candle.Close)

    def pnlmaxmin(self, maxmin, firstonly=False):
        return f.getPnl(self.side, self.entryprice, self.extremum(self.side * maxmin, firstonly))

    def isgood(self):
        ans = True if self.pnlfinal > 0 else False
        return ans

    def isstopped(self):
        ans = True if self.pnlmaxmin(-1) < self.strat.stoppercent else False
        return ans

    def exitdate(self):
        return self.candles[self.duration()].timestamp
    
    def rescaleorders(self, balance):
        # need to fix 'orders' for trade_chop
        for order in self.orders:
            order.rescalecontracts(balance=balance, conf=self.conf)
    
    def extremum(self, highlow, firstonly=False):
        
        # entry candle
        c = self.candles[0]
        with f.Switch(self.status * highlow) as case:
            if case(1, -2):
                if highlow == 1:
                    ext = c.High
                elif highlow == -1:
                    ext = c.Low
            elif case(-1, 2):
                ext = self.entryprice

        if firstonly: return ext

        # middle candles
        for i in range(1, self.duration() - 2):
            c = self.candles[i]
            if highlow == 1:
                if c.High > ext: ext = c.High
            elif highlow == -1:
                if c.Low < ext: ext = c.Low

        # exit candle
        c = self.candles[self.duration() - 1]
        with f.Switch(self.status * highlow) as case:
            if case(-1, 2):
                fExt = self.exitprice
            elif case(1, -2):
                if highlow == 1:
                    fExt = c.High
                elif highlow == -1:
                    fExt = c.Low
        
        ext = fExt if (fExt - ext) * highlow > 0 else ext

        return ext

    def printcandles(self):
        for c in self.candles:
            print(
                c.CloseTime,
                c.Open,
                c.High,
                c.Low,
                c.Close)

    def printorders(self, orders=None):
        
        if orders is None:
            orders = self.allorders()

        data = []
        headers = ['IDX', 'Type', 'Side', 'Price', 'Cont', 'Active', 'Cancelled', 'Filled']

        for o in orders:
            ordtype = o.ordarray.letter() if not o.ordarray is None else o.ordtype 

            data.append([
                o.index,
                ordtype,
                o.side,
                o.price,
                o.contracts,
                o.active,
                o.cancelled,
                o.filled])

        table = columnar(data, headers, no_borders=True, justify='r')
        print(table)

class Trade_TrendRev(Trade):
    def __init__(self):
        super().__init__()
        self.stopped = False
    
    def closeprice(self):
        c = self.candle
        price = c.trendrev_high if self.side == 1 else c.trendrev_low

        return round(price * (1 + self.slippage * self.side),0)
    
    def enter(self, temp=False):
        if not temp:
            self.strat.trades.append(self)

        # c = self.strat.candle
        # self.stoppercent = c.norm * -1
        self.stoppercent = self.strat.stoppercent
        # self.slippage = c.norm / 80
        self.slippage = self.strat.slippage

        limitbuyprice = self.entrytarget * (1 + self.slippage * self.side * -1)
        limitcloseprice = self.closeprice()
        self.stoppx = f.getPrice(self.stoppercent, limitbuyprice, self.side)

        contracts = int(self.targetcontracts * self.conf)

        self.limitopen = Order(
                    price=limitbuyprice,
                    side=self.side,
                    contracts=contracts,
                    activate=True,
                    ordtype=1,
                    ordtype2='Limit',
                    name='limitopen',
                    trade=self)

        self.stop = Order(
                    price=self.stoppx,
                    side=self.side * -1,
                    contracts=contracts * -1,
                    activate=False,
                    ordtype=2,
                    ordtype2='Stop',
                    name='stop',
                    trade=self)

        self.limitclose = Order(
                    price=limitcloseprice,
                    side=self.side * -1,
                    contracts=contracts * -1,
                    activate=False,
                    ordtype=3,
                    ordtype2='Limit',
                    name='limitclose',
                    trade=self)

        self.orders.extend([self.limitopen, self.stop, self.limitclose])
    
    def checkorders(self, c):
        self.addCandle(c)

        for o in self.orders:
            if o.active and not o.filled:
                o.check(c)

                # if order not filled after 4 candles, fill at close price
                if o.ordtype == 1 and self.duration() == 4 and not o.filled:
                    o.fill(c=c, price=c.Close)

                if o.filled:
                    if o.ordtype == 1:
                        self.filledcontracts = o.contracts
                        self.limitclose.active = True
                        self.stop.active = True
                    elif o.ordtype == 2:
                        self.limitclose.cancel() #make limitclose filledtime be end of trade
                        self.stopped = True
                    elif o.ordtype == 3:
                        self.stop.cancel()

        # trade stays active until pxlow is hit, strat controlls
            
        # adjust limitclose for next candle, this is probs out of sync with strat
        self.limitclose.price = self.closeprice()        

        # filling order sets the trade's actual entryprice
        # filling close or stop order sets trade's exit price

    def allorders(self):
        return [self.limitopen, self.stop, self.limitclose]

class Trade_Trend(Trade):
    def __init__(self):
        super().__init__()

    def enter(self):       
        # MeanRev only
        if abs(self.status) == 2:
            self.stoppx = f.getPrice(self.strat.stoppercent, self.entryprice, self.side)

    def exit(self, price):
        self.exitprice = price
        if not self.sym.stratactive:
            self.sym.account.modify(f.getPnlXBT(self.contracts, self.entryprice, self.exitprice, self.sym.altstatus), self.sym.curcandle.CloseTime)
        
        self.strat.trades.append(self)
        self.exittrade()
        
class Trade_Chop(Trade):
    def __init__(self, candle):
        super().__init__()
        self.numorders = 4
        self.candle = candle
            
    def enter(self):
        self.anchorstart = self.entryprice
        self.entryprice = 0
        
        # strat = self.strat
        # if strat.tradecount() > 0:
        #     if strat.trades[strat.tradecount() - 1].pnlfinal > 0:
        #         self.targetcontracts = int(self.targetcontracts*1.2)
        #     else:
        #         self.targetcontracts = int(self.targetcontracts*0.8)

        c = self.candle
        self.strat.trades.append(self)
        
        self.anchorprice = self.strat.getAnchorPrice(self.anchorstart, c.norm, self.status)

        lst = self.strat.getNextOrdArrays(self.anchorprice, c, self.status, self)
        self.orders = lst[0]
        self.stops = lst[1]
        self.takeprofits = lst[2]

    def exit(self):
        self.filledcontracts = self.orders.filledcontracts
        self.exittrade()
        
    def checkorders(self, candle):
        self.addCandle(candle)

        if self.duration() == 5: # 5 is arbitrary
            self.deactivateorders()
        elif self.duration() == 40:
            self.closeposition()
        
        self.orders.checkorders(candle)
        self.stops.checkorders(candle)
        self.takeprofits.checkorders(candle)
        
        if not self.orders.active and self.contracts == 0:
            self.active = False # > then exit trade??

        if (not self.stops.active) or (not self.takeprofits.active):
            self.active = False

    def deactivateorders(self, closeall=False):
        if not closeall:
            for i, order in enumerate(self.orders.orders):
                if not order.filled:
                    order.cancel()
                    self.takeprofits.orders[i].cancel()
                    self.stops.orders[i].cancel()
        else:
            for order in self.allorders():
                if not order.filled:
                    order.cancel()

    def allfilled(self):
        return '{}-{}-{}'.format(
            self.orders.strfilled(),
            self.stops.strfilled(),
            self.takeprofits.strfilled())

    def allorders(self):
        lst = []
        lst.extend(self.orders.orders)
        lst.extend(self.stops.orders)
        lst.extend(self.takeprofits.orders)        
        return lst

    def printallorders(self):
        self.strat.printorders(self.allorders())


# ORDER
class Order():
    def __init__(self, price, side, contracts, ordtype, ordarray=None, trade=None, sym=None,  activate=False, index=0, symbol='', name='', ordtype2=''):

        self.ordarray = ordarray
        self.trade = trade
        self.sym = sym

        self.symbol = symbol
        self.name = name
        self.orderID = ''
        self.execInst = ''
        self.ordtype2 = ordtype2        

        if not self.ordarray is None:
            self.trade = self.ordarray.trade

        if not self.trade is None:
            self.sym = self.trade.strat.sym

        # live trading
        if not self.sym is None:
            self.decimalfigs = self.sym.decimalfigs
            self.symbol = symbol
            self.symbolbitmex = self.sym.symbolbitmex
        else:
            self.decimalfigs = 0
            self.symbolbitmex = self.symbol
            
        self.decimaldouble = float('1e-{}'.format(self.decimalfigs))
        self.index = index
        self.side = side
        self.price = self.finalprice(price)
        self.pxoriginal = self.price
        self.contracts = contracts
        self.ordtype = ordtype
        self.active = activate
        self.activenext = False
        self.filled = False
        self.marketfilled = False
        self.cancelled = False
        self.filledtime = None            

        self.enterexit = -1 if (ordtype == 1 or ordtype == 2) else 1
        self.addsubtract = -1 if (ordtype == 2 or ordtype == 3) else 1
        if not self.trade is None:
            self.direction = self.trade.side * self.enterexit
        
        if self.name == 'stopbuy':
            self.execInst = 'IndexPrice'
        elif self.name == 'stopclose' or self.name[0] == 'S':
            self.execInst = 'Close,IndexPrice'
        elif self.name[0] == 'T':
            self.execInst = 'Close'
        
        self.matched = False
        self.livedata = []
        self.setkey()

    def setname(self, name):
        self.name = name
        self.setkey()

    def setkey(self):
        self.key = f.key(self.symbolbitmex, self.name, self.side, self.ordtype)
        self.clOrdID = '{}-{}'.format(self.key, int(time()))        

    def check(self, c):
        checkprice = c.High if self.direction == 1 else c.Low
        
        if self.direction * (self.price - checkprice) <= 0:
            self.fill(c=c)
            
    def open(self):
        trade = self.trade
        contracts = self.contracts

        if contracts == 0: return

        trade.entryprice = (trade.entryprice * trade.contracts + self.price * contracts) / (trade.contracts + contracts)
        trade.contracts += contracts            
            
    def close(self):
        self.trade.closeorder(price=self.price, contracts=self.contracts) 
            
    def fill(self, c, price=None):
        self.filled = True
        self.filledtime = c.CloseTime

        if not price is None:
            self.price = price
            self.marketfilled = True

        self.open() if self.addsubtract == 1 else self.close()
            
    def printself(self):
        print(
            self.index,
            self.ordarray.ordtype,
            self.side,
            self.price,
            self.contracts,
            self.active,
            self.cancelled,
            self.filled)

    def cancel(self):
        self.active = False
        self.cancelled = True
        self.filledtime = self.sym.curcandle.CloseTime
        if not self.ordarray is None:
            self.ordarray.openorders -= 1

    def rescalecontracts(self, balance, conf=1):
        self.contracts = int(conf * f.getContracts(
                        xbt=balance,
                        leverage=self.trade.strat.lev,
                        entryprice=self.price,
                        side=self.side,
                        isaltcoin=self.sym.altstatus))

    def intakelivedata(self, livedata):
        self.livedata = livedata
        self.orderID = livedata['orderID']
        self.ordType = livedata['ordType']

    def amendorder(self):
        m = {}
        m['orderID'] = self.orderID
        m['symbol'] = self.sym.symbolbitmex
        m['orderQty'] = self.contracts

        with f.Switch(self.ordtype2) as case:
            if case('Limit'):
                m['price'] = self.finalprice()
            elif case('Stop'):
                m['stopPx'] = self.finalprice()
                
            # elif case('StopLimit'):
            #     m['price'] = self.finalprice()
                
            #     self.stopPx = self.trade.orders.orders[self.index].price
            #     m['stopPx'] = self.finalprice(self.stopPx)

        if not self.execInst == '':
            m['execInst'] = self.execInst
        
        return m

    def neworder(self):
        m = {}
        m['symbol'] = self.symbolbitmex
        m['orderQty'] = self.contracts
        m['clOrdID'] = self.clOrdID
        
        with f.Switch(self.ordtype2) as case:
            if case('Limit'):
                m['price'] = self.finalprice()
            elif case('Stop'):
                m['stopPx'] = self.finalprice()
            elif case('Market'):
                m['ordType'] = self.ordtype2
            # elif case('StopLimit'):
            #     m['price'] = self.finalprice()
        
        if not self.execInst == '':
            m['execInst'] = self.execInst
        
        return m
    
    def finalprice(self, price=None):
        if price is None:
            price = self.price

        return round(round(price, self.decimalfigs) + self.decimaldouble * self.side * -1, self.decimalfigs) #slightly excessive rounding
     
class OrdArray():
    
    def getFraction(self, n):
        if n == 0:
            return 1 / 6
        elif n == 1:
            return 1 / 4.5
        elif n == 2:
            return 1 / 3.6
        elif n == 3:
            return 1 / 3

    def getOrderPrice(self, n):
        if not self.outerprice is None:
            n += 1
        
        price = self.anchorprice * (1 + self.orderspread * n * self.trade.status * self.enterexit)
        
        return round(price, self.decimalfigs)
    
    def __init__(self, ordtype, anchorprice, orderspread, trade, activate=False, outerprice=None):
        self.ordtype = ordtype
        self.anchorprice = anchorprice
        self.orderspread = orderspread
        self.trade = trade
        self.outerprice = outerprice
        
        if not outerprice is None:
            self.pricerange = abs(self.outerprice - self.anchorprice)
            self.orderspread = (self.pricerange / (trade.numorders + 1))  / anchorprice

        self.decimalfigs = self.trade.strat.sym.decimalfigs

        self.orders = []
        self.active = True
        # self.enterexit = -1 if (ordtype == 1 or ordtype == 2) else 1
        # self.addsubtract = -1 if (ordtype == 2 or ordtype == 3) else 1
        # self.direction = self.trade.status * self.enterexit
        self.side = self.trade.side * self.addsubtract

        self.filled = False
        self.filledorders = 0
        self.filledcontracts = 0
        self.numorders = self.trade.numorders
        self.openorders = self.numorders

        self.maxprice = anchorprice * (1 + self.direction * ((self.numorders - 1) * orderspread))

        # init and add all orders to self (ordArray)
        modi = 'lwr' if self.trade.side == 1 else 'upr'

        with f.Switch(self.ordtype) as case:
            if case(1):
                ordtype2 = 'Limit'
            elif case(2):
                ordtype2 = 'Stop'
            elif case(3):
                ordtype2 = 'Limit'

        for i in range(self.numorders):
            price = self.getOrderPrice(i)
            contracts = int(round(self.getFraction(i) * self.trade.targetcontracts * self.addsubtract, 0))

            order = Order(
                        price=price,
                        side=self.side,
                        contracts=contracts,
                        ordarray=self,
                        activate=activate,
                        index=i,
                        symbol=self.trade.strat.sym.symbol,
                        name='{}{}{}'.format(self.letter(), i + 1, modi),
                        ordtype=ordtype2,
                        sym=self.trade.strat.sym)

            self.orders.append(order)
    
    def checkorders(self, candle):
        if not self.active:
            return
        
        if self.ordtype > 1 and self.trade.contracts == 0:
            return
        
        for i, order in enumerate(self.orders):
            
            if order.active and not order.filled:
                order.check(candle)
                if order.filled:
                    if self.ordtype == 1:
                        self.trade.stops.orders[i].active = True
                        self.trade.takeprofits.orders[i].activenext = True
                    elif self.ordtype == 2:
                        self.trade.takeprofits.orders[i].cancel()
                    elif self.ordtype == 3:
                        self.trade.stops.orders[i].cancel()

                    self.filledorders += 1
                    self.filledcontracts += order.contracts
            elif order.activenext and not order.cancelled:
                # delay for 1 period
                order.activenext = False
                order.active = True
        
        if self.filledorders == self.openorders:
            self.filled = True
            self.active = False

    def letter(self):
        with f.Switch(self.ordtype) as case:
            if case(1):
                return 'O'
            elif case(2):
                return 'S'
            elif case(3):
                return 'T'

    def strfilled(self):
        return '{}{}{}'.format(self.letter(), self.filledorders, self.openorders)
    
    def getUnfilledOrders(self, targetcontracts=None, actualcontracts=0):
        lst = []
        # print('actualcontracts: {}'.format(actualcontracts))
        for i, order in enumerate(self.orders):
            
            # rescale to contracts to reflect actual user balance
            if not targetcontracts is None:
                order.contracts = int(round(self.getFraction(order.index) * targetcontracts * self.addsubtract, 0))

            if not (order.cancelled or order.filled):
                
                if self.ordtype == 1:
                    # order
                    lst.append(order)
                else:
                    # stops - check if matching order NOT filled
                    # print(self.trade.orders.orders[i].filled)
                    if not self.trade.orders.orders[i].filled:
                        # good, stops should be active
                        if self.ordtype == 2:
                            lst.append(order)
                    else:
                        # Order SHOULD be filled, check it
                        # loop from max filled order to current order, check if we have enough contracts
                        ordarray = self.trade.orders
                        maxfilled = ordarray.filledorders
                        # print('i: {}, maxfilled: {}'.format(i, maxfilled))
                        remainingcontracts = actualcontracts
                        for y in range(maxfilled - 1, i, -1):
                            # print(y, remainingcontracts, ordarray.orders[y].contracts)
                            remainingcontracts -= ordarray.orders[y].contracts

                        # print('remainingfinal: {}, order.contr: {}, side: {}'.format(remainingcontracts, order.contracts, ordarray.side))
                        if (remainingcontracts - order.contracts * -1) * ordarray.side >= 0:
                            lst.append(order)
                            # also check to fill the last order no matter what??
        return lst

    def printorders(self):
        for order in self.orders:
            order.printself()


# OTHER
class Txn():
    def __init__(self):
        self.amount = 0
        self.timestamp = None
        self.acctbalance = 0
        self.percentchange = 0

    def printTxn(self):
        # Debug.Print Format(Me.DateTx, "yyyy-mm-dd HH"), Me.AcctBalance, Me.Amount
        pass

class Candle():
    def __init__(self, row):
        self.row = row

    def dHC(self):
        return self.row.High - self.row.Close
    
    def dLC(self):
        return self.row.Low - self.row.Close
    
    def percentOCd(self):
        return (self.row.Close - self.row.Open) / self.row.Open

    def percentOC(self):
        return f.percent(self.percentOCd())
            
    def size(self):
        return abs(self.row.High - self.row.Low)
        
    def convertthis(self):
        # Public Function isSwingFail(oSym As cSymBacktest) As Boolean
        #     MinSwing = 0.5
        #     MinCloseEma = 0.005
        #     Dim y As Integer
            
        #     aCandles = 24
        #     For y = Me.i - aCandles To Me.i - 1
        #         AvgCandleSize = oSym.Candle(y).Size + AvgCandleSize
        #     Next y
        #     AvgCandleSize = AvgCandleSize / aCandles
            
        #     If TailSize > AvgCandleSize Then
        #         dCloseEma = SwingType * (Clse - ema10) / ema10
        #         TailPercent = TailSize / Size
        #         If (TailPercent > MinSwing And dCloseEma > MinCloseEma) _
        #             Or (TailPercent > 0.3 And TailSize > 1.75 * AvgCandleSize) _
        #             Then isSwingFail = True
        #     End If
            
        # End Function

        # Public Property Get SwingType() As Integer
        #     If Me.Clse > Me.Opn Then
        #         SwingType = 1
        #         Else
        #         SwingType = -1
        #     End If
        # End Property
        # Public Property Get TailSize() As Double
        #     Select Case SwingType
        #         Case 1
        #             TailSize = High - Clse
        #         Case -1
        #             TailSize = Clse - Low
        #     End Select
        # End Property
        # Public Property Get TailSizeOpp() As Double
        #     Select Case SwingType
        #         Case 1
        #             TailSizeOpp = Clse - Low
        #         Case -1
        #             TailSizeOpp = High - Clse
        #     End Select
        # End Property
        # Public Function printCandle() As String
        #     Select Case SwingType
        #         Case 1
        #             bodyFill = " "
        #             bodyHigh = Clse
        #             bodyLow = Opn
        #         Case -1
        #             bodyFill = ":"
        #             bodyHigh = Opn
        #             bodyLow = Clse
        #     End Select
            
        #     '-------a[      ]b---c
        #     upWick = Round(High - bodyHigh, 0)
        #     downWick = Round(bodyLow - Low, 0)
        #     body = Round(bodyHigh - bodyLow, 0)
            
        #     a = Normalize(CDbl(downWick), 500, 5, 100, 1)
        #     b = Normalize(CDbl(downWick + body), 500, 5, 100, 1)
        #     c = Normalize(CDbl(downWick + body + upWick), 500, 5, 100, 1)
            
        #     For i = 1 To a
        #         strCandle = strCandle & "-"
        #     Next i
        #     strCandle = strCandle & "["
        #     For i = a To b
        #         strCandle = strCandle & bodyFill
        #     Next i
        #     strCandle = strCandle & "]"
        #     For i = b To c
        #         strCandle = strCandle & "-"
        #     Next i
        #     'strCandle = "|" & strCandle & "|"
        #     printCandle = strCandle
        # End Function
        pass
