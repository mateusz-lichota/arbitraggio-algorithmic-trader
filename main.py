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
        
        # if we have too big imbalance, it's okay to trade 
        # at 0 profit to reduce the imbalance
        need_balancing = position[buyside] < -50 or position[sellside] > 50
        
        min_pm = -0.01 if need_balancing else 0.01
        
        # check if the trade will be profitable 
        pm = bid.price - ask.price
        if (pm > min_pm):
            volume = min(min(bid.volume, ask.volume), min(500-position[buyside], position[sellside]+500))
            if volume < 1:
                return
            
            # if net position is nonzero, attempt to buy/sell
            # more on one side to bring it closer to zero.
            # Additionally, make the trade bringing total_position
            # closer to zero first, as the first operation has
            # higher chance of success.
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
