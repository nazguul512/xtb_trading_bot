
# XTB_trading_bot

XTB_trading_bot is exactly what its name implies. A bot written in Python, works with XTB broker using the API.py file (a wrapper for XTB API, not written by me).


## Documentation

At this moment, the bot doesn't trade by itself, it only takes the tickers available from the XTB broker, applies a RSI + BB strategy and sends all tickers for Buy and Sell through a channel in Telegram.
The original link for the wrapper is here https://github.com/caiomborges/Python-XTB-API but I decided to included it in my files for a quicker setup.
I'm not gonna lie, my journey in Python is in its infancy steps, so at the moment ChatGPT is a great help to unblock me and improve my code where needed.


## Setup

After installing all the libraries needed (sorry, at this point I don't have enough experience with pip or such, but I will work on making a requirements.txt), you will need to setup a telegram bot channel in order for you to receive the notifications send by the bot.
 - In the API.py wrapper you will need to modify the file at line 553 for which kind of XTB account you are using, demo or real.
 - For setting up a telegram bot, follow this link:
   https://pypi.org/project/telegram-send/
 - In Instalation section you have a guide on hot to install the library and also how to setup the bot in telegram to provide the library all that is needed. Warning, I sugest using v 0.24
 - If you use a gspread like I do and want to keep it updated, you can use this guide here: https://codoid.com/automation-testing/gspread-python-tutorial/
   The key needs to be put in a file called pybotnasq_tok.json
## Next Steps

- make a requirements.txt for easy install of dependencies
- make script check dinamically if market is closed in that dinamically
- make script start and end dinamically, based on system set tmz
- make script asks at first run if you have available a spredsheed you want to update
- make script asks at first run if you have a telegram bot and want to use one for notifications
- use different telegram bot library and create a fully fledged bot that also accepts various commands (dinamically updating portfolio and wishlist, dinamically updating spreadsheet when sold or bought stocks, etc)
- remove portfolio and wishlist as files, include them as config parameters
- make in config an argument of demo/real for the API.py
- more TBA as soon as I think of

## Next Next Steps :grin:

- include new buy/sell strategies and let user choose which one is to be run
- make user choose if he wishes to only have notifications or give bot full authonomy to make trades
- make config arguments for full authonomy trades
- implement bot to be fully authonomous
- more TBA as soon as I think of

### Support
If you would like to support this by having a 'nice to have' that i haven't thought of, open an Issue and we'll discuss about it.

You can also support me here if you so desire:
<a href="https://www.buymeacoffee.com/nazguul512" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-yellow.png" alt="Buy Me A Coffee" height="41" width="174"></a>