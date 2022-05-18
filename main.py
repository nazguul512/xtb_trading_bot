from tradingview_ta import *
import urllib.parse
import pandas
from yahoo_fin import stock_info
from termcolor import colored
import time
import telegram_send

googleSheetId = '1bCOpwbWV49_XIrmJMjDHqiLNldqgttNxzvvgpNT79oI'
worksheetName = '1. Revolut stocks list'
sheetURL = 'https://docs.google.com/spreadsheets/d/{0}/gviz/tq?tqx=out:csv&sheet={1}'.format(
    googleSheetId,
    urllib.parse.quote_plus(worksheetName)
)

ticker_list = pandas.read_csv(sheetURL, usecols=['Symbol'])
df = pandas.read_csv(sheetURL, usecols=['Symbol', 'Market'])
tickers = ticker_list.to_string(header=False, index=False).split()
trading_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
first_time_run = 0
current_sell_list = []
current_buy_list = []
previous_sell_list = []
previous_buy_list = []
diff_sell_list = []
diff_buy_list = []

while True:
    day_of_trade = time.strftime("%A")
    time_of_trade = time.strftime("%H%M%S")
    time_of_trade = int(time_of_trade)
    message_for_telegram = time.strftime("%d.%m.%Y %H:%M:%S\n")

    if time_of_trade >= 163001 and time_of_trade <= 164001:
        first_time_run = 1

    if day_of_trade in trading_days and time_of_trade >= 163001 and time_of_trade <= 222959:
        
        my_portfolio_file = open("portofoliu.txt", "r")
        content_portofoliu = my_portfolio_file.read()
        portofoliu = content_portofoliu.split(" ")
        my_portfolio_file.close()

        my_wishlist_file = open("wishlist.txt", "r")
        content_wishlist = my_wishlist_file.read()
        wishlist = content_wishlist.split(" ")
        my_wishlist_file.close()

        for ticker in tickers:
            market_data = df.query('Symbol == @ticker').loc[0:, 'Market']
            market_exchange = market_data.to_string(header=False, index=False)
            try:
                stock_data = TA_Handler(
                    symbol=ticker,
                    exchange=market_exchange,
                    screener="america",
                    interval=Interval.INTERVAL_1_DAY
                )
                tickerRSI = stock_data.get_analysis().indicators["RSI"]
                tickerBBU = stock_data.get_analysis().indicators["BB.upper"]
                tickerBBL = stock_data.get_analysis().indicators["BB.lower"]
            except:
                print(colored("Couldn't get stock data for {}", "yellow").format(ticker))

            try:
                current_price = stock_info.get_live_price(ticker)
            except:
                print(colored("Couldn't get price data for {}", "yellow").format(ticker))

            try:
                if tickerRSI >= 70 and current_price >= tickerBBU:
                    if ticker in portofoliu:
                        print(colored("Signal to sell {}", "red", attrs=["bold", "underline"]).format(ticker))
                        message_time = time.strftime("%d.%m.%Y %H:%M:%S\n")
                        alert_message = "<b>!!! " + message_time + "You have this " + ticker + "\nMaybe SELL</b>"
                        telegram_send.send(messages=[alert_message], parse_mode="html")
                    else:
                        print(colored("Signal to sell {}", "red").format(ticker))
                    current_sell_list.append(ticker)
                if tickerRSI <= 30 and current_price <= tickerBBL:
                    if ticker in portofoliu:
                        print(colored("Signal to buy {}", "green", attrs=["bold", "underline"]).format(ticker))
                        message_time = time.strftime("%d.%m.%Y %H:%M:%S\n")
                        alert_message = "<b>!!! " + message_time + "You have this " + ticker + "\nBUY More!!!</b>"
                        telegram_send.send(messages=[alert_message], parse_mode="html")
                    elif ticker in wishlist:
                        print(colored("Signal to buy {}", "blue", attrs=["bold", "underline"]).format(ticker))
                        message_time = time.strftime("%d.%m.%Y %H:%M:%S\n")
                        alert_message = "<b>!!! " + message_time + "You want this " + ticker + "\nBUY Now!</b>"
                        telegram_send.send(messages=[alert_message], parse_mode="html")
                    else:
                        print(colored("Signal to buy {}", "green").format(ticker))
                    current_buy_list.append(ticker)
            except:
                print(colored("Couldn't calculate data for {}", "cyan").format(ticker))

        if first_time_run == 1:
            if not current_sell_list:
                message_for_telegram = message_for_telegram + "Nothing to sell now\n"
            else:
                for ticker_to_sell in current_sell_list:
                    message_for_telegram = message_for_telegram + "Sell signal for: " + ticker_to_sell + "\n"

            if not current_buy_list:
                message_for_telegram = message_for_telegram + "Nothing to buy now\n"
            else:
                for ticker_to_buy in current_buy_list:
                    message_for_telegram = message_for_telegram + "Buy signal for: " + ticker_to_buy + "\n"

            telegram_send.send(messages=[message_for_telegram], parse_mode="html")
            first_time_run = 0
            previous_sell_list = current_sell_list.copy()
            previous_buy_list = current_buy_list.copy()
            current_sell_list.clear()
            current_buy_list.clear()
        else:
            diff_sell_list = [x for x in current_sell_list if x not in previous_sell_list]
            diff_buy_list = [x for x in current_buy_list if x not in previous_buy_list]
            
            if diff_sell_list or diff_buy_list:
                message_for_telegram = "<b><u>Update at " + message_for_telegram + "</u></b>\n"
            else:
                continue

            if diff_sell_list:
                for ticker_to_sell in diff_sell_list:
                    if ticker_to_sell in portofoliu:
                        message_for_telegram = message_for_telegram + "<b><u>Sell signal for: " + ticker_to_sell + "</u></b>\n"
                    elif ticker_to_sell in wishlist:
                        message_for_telegram = message_for_telegram + "<b><i>Sell signal for: " + ticker_to_sell + "</i></b>\n"
                    else:
                        message_for_telegram = message_for_telegram + "Sell signal for: " + ticker_to_sell + "\n"

            if diff_buy_list:
                for ticker_to_buy in diff_buy_list:
                    if ticker_to_buy in portofoliu:
                        message_for_telegram = message_for_telegram + "<b><u>Buy signal for: " + ticker_to_buy + "</u></b>\n"
                    elif ticker_to_buy in wishlist:
                        message_for_telegram = message_for_telegram + "<b><i>Buy signal for: " + ticker_to_buy + "</i></b>\n"
                    else:
                        message_for_telegram = message_for_telegram + "Buy signal for: " + ticker_to_buy + "\n"

            telegram_send.send(messages=[message_for_telegram], parse_mode="html")
            previous_sell_list.clear()
            previous_buy_list.clear()
            previous_sell_list = current_sell_list.copy()
            previous_buy_list = current_buy_list.copy()
            current_sell_list.clear()
            current_buy_list.clear()
