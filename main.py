import time
from datetime import datetime
from optibook.synchronous_client import Exchange
from optibook.common_types import PriceVolume
import logging
logger = logging.getLogger('client')
logger.setLevel('ERROR')

pha = 'PHILIPS_A'
phb = 'PHILIPS_B'

e = Exchange()
a = e.connect()

print("Setup was successful, entering loop")



# The idea for this strategy is connected to a 'minimum profit margin curve':
min_pm_curve = [(0, 0.15), (200, 0.25), (300, 0.35), (400, 0.45), (450, 0.65)]

# Because of the limits for long and short buying stocks (up to 500), the algorithm needs to
# make trades which will both earn money instantly, and leave some limit for the possibility
# of even larger profits. Therefore, the minimum profit margin at which the algorithm will trade
# is related to the stock purchasing limits it has left.
#
# The minimum profit margin vs our position on the stock to be bought is presented below:
#
#   0.7                                                                 *******
#   0.6                                                                 *
#   0.5                                                          ********
#   0.4                                               ************
#   0.3                                   *************
#   0.2              **********************
#   0.1              *
#   0.0   ************
#       -100 ------- 0 ------ 100 ------- 200 ------- 300 ------ 400 -------- 500

# It can be seen that the closer we are to the limit, the higher profit margin we require,
# in order to avoid situations where we exhaust the limit and there is still possibility
# to trade at large profits.
# Additionally, when we are short on the stock that we are considering buying, the minimum pm
# is zero, in order to 'zero out' our short position with the long position on the other stock



# instr is 0 when buying PHA and selling PHB, 1 otherwise
# books is [book_a, book_b]
# position is (pha, phb)
def try_to_trade(instr, books, position):
    stock_to_buy  = phb if instr else pha
    stock_to_sell = pha if instr else phb
    buyside = instr
    sellside = 1-instr
    
    if (books[sellside].bids and books[buyside].asks):
        bid = books[sellside].bids[0]
        ask = books[buyside].asks[0]
        
        # get the appriopriate min_pm from the curve. The starting value of
        # min_pm = -0.05 means that we will only trade for pm of 0.0 or more
        min_pm = -0.05
        for boundary, pm in min_pm_curve:
            if (position[buyside] > boundary) or (position[sellside] < -boundary):
                min_pm = pm
            else:
                break
        
        # check the achievable profit margin
        pm = bid.price - ask.price
        if (pm > min_pm):
            # essentially, do not trade so much as to exceed limits either on buyside or sellside
            volume = min((bid.volume, ask.volume, 500-position[buyside], position[sellside]+500))
            if volume < 1:
                return
            
            # if net position is nonzero, attempt to buy/sell
            # more on one side to bring it closer to zero.
            # Additionally, make the trade bringing total_position
            # closer to zero first, as the first operation has
            # higher chance of success,l so this order of operations
            # will on average reduce the abs(net_position).
            net_position = position[0] + position[1]
            if net_position >= 0:
                if (bid.volume > volume):
                    volume = min(bid.volume, volume+net_position)
                e.insert_order(stock_to_sell, price=bid.price, volume=volume, side='ask', order_type='ioc')
                e.insert_order(stock_to_buy,  price=ask.price, volume=max(1, volume - net_position),  side='bid', order_type='ioc')
            else:
                if (bid.volume > volume):
                    volume = min(ask.volume, volume-net_position)
                e.insert_order(stock_to_buy,  price=ask.price, volume=volume,  side='bid', order_type='ioc')
                e.insert_order(stock_to_sell, price=bid.price, volume=max(1, volume + net_position), side='ask', order_type='ioc')

def timestamp():
    return datetime.utcnow().isoformat() + ' | '
    
def summarize_trades(trades):
    # instrument: [net cash, net volume]
    trades_sum = {pha: [0, 0], 
                  phb: [0, 0]}
    for t in trades:
        sgn_vol  = (1 if t.side == 'bid' else -1) * t.volume
        sgn_cash = (-sgn_vol) * t.price
        
        trades_sum[t.instrument_id][0] += sgn_cash
        trades_sum[t.instrument_id][1] += sgn_vol
    
    for instr, net in trades_sum.items():
        if (net != [0,0]):  
            print(timestamp() + f"{'BOUGHT' if net[1]>0 else 'SOLD  '} {abs(net[1])} lots of {'PHA' if instr==pha else 'PHB'} for {-(net[0]/net[1]):8.2f}")
    
    # this function could also export statistics and data for further analysis if it were nexessary
            
last_trades_update = time.time()
last_position = (0, 0)
done = False
while not done:
    try:
        while not e.is_connected():
            print(timestamp() + 'disconnected, trying to reconnect...')
            time.sleep(1)
            e.connect()
            
        positions = e.get_positions()
        position = (positions.get(pha), positions.get(phb))
        
        if position != last_position:
            last_position = position
            trades = e.poll_new_trades(pha) + e.poll_new_trades(phb)
            if trades:
                summarize_trades(trades)
            print(timestamp() + f"==> POSITION: PHA: {position[0]}, PHB: {position[1]}")
        
        books = e.get_last_price_book(pha), e.get_last_price_book(phb)
        try_to_trade(0, books, position) # buy PHA, sell PHB
        try_to_trade(1, books, position) # buy PHB, sell PHA
        
    except KeyboardInterrupt:
        done = True
    except Exception as exc:
        print(timestamp() + "error: " + str(exc))
