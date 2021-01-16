import chalk
from datetime import datetime
import json
import pandas as pd
from pycoingecko import CoinGeckoAPI
import time
from tqdm import tqdm
from web3 import Web3


cg = CoinGeckoAPI()


#-------------------------------------------------------------------------------
# Utils
#-------------------------------------------------------------------------------

currenttime = lambda: chalk.white(datetime.now().strftime("[%m/%d/%Y %H:%M:%S]"))


def info(msg, **kwargs):
    output = [ currenttime(), chalk.green("INFO"), msg ]
    output += [ "{}={}".format(chalk.blue(key), val) for key, val in kwargs.items() ]
    output = " ".join(output)

    with open(LOG, "a") as f:
        f.write(output + "\n")

    print(output)


def warn(msg, **kwargs):
    output = [ currenttime(), chalk.yellow("WARN"), msg ]
    output += [ "{}={}".format(chalk.blue(key), val) for key, val in kwargs.items() ]
    output = " ".join(output)

    with open(LOG, "a") as f:
        f.write(output + "\n")

    print(output)


def sleepWithProgressBar(seconds):
    info("Sleeping", seconds=seconds)
    for i in tqdm(range(seconds)):
        time.sleep(1)


#-------------------------------------------------------------------------------
# Values
#-------------------------------------------------------------------------------

DATA_DIR = "./data"
LOG = "./bot.log"
INTERVAL = 60 * 60  # 1 hr

from secrets import INFURA_PROJECT_ID, USER
info("Loaded secrets", INFURA_PROJECT_ID=INFURA_PROJECT_ID, USER=USER)

INFURA_RPC_URL = "https://mainnet.infura.io/v3/{}".format(INFURA_PROJECT_ID)

with open("./UniswapV2Pair.json") as f:
    UNISWAP_V2_PAIR_ABI = json.load(f)

POOL_INFO = {
    "RUNE-ETH": {
        "abi": UNISWAP_V2_PAIR_ABI,
        "address": "0xcc39592f5cB193a70f262aA301f54DB1d600e6Da",
        "token0": {
            "id": "thorchain",
            "symbol": "RUNE",
            "decimals": 18
        },
        "token1": {
            "id": "ethereum",
            "symbol": "ETH",
            "decimals": 18
        }
    },
    "RUNE-USDT": {
        "abi": UNISWAP_V2_PAIR_ABI,
        "address": "0xD279F1351D2828d559BC7a6b82c322c4d5665bEd",
        "token0": {
            "id": "thorchain",
            "symbol": "RUNE",
            "decimals": 18
        },
        "token1": {
            "id": "tether",
            "symbol": "USDT",
            "decimals": 6
        }
    }
}


#-------------------------------------------------------------------------------
# Instances
#-------------------------------------------------------------------------------

w3 = Web3(Web3.HTTPProvider(INFURA_RPC_URL))
info("Web3 instance created", blockNumber=w3.eth.blockNumber)

pools = {
    name: w3.eth.contract(
        abi=pool["abi"],
        address=pool["address"]
    )
    for name, pool in POOL_INFO.items()
}
info(
    "Contract instances created",
    runeEthPool=pools["RUNE-ETH"].address,
    runeUsdtPool=pools["RUNE-USDT"].address
)


#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

def fetchData(name, pool):
    info("Started fetching data for pool", name=name)

    filename = "{}/{}.csv".format(DATA_DIR, name)
    try:
        data = pd.read_csv("{}/{}.csv".format(DATA_DIR, name)).to_dict("records")
        info("Loaded previous data", filename=filename)

        lastSavedTimestamp = data[-1]["timestamp"]
        now = int(time.time())
        diff = INTERVAL - (now - lastSavedTimestamp)
        if diff > 0:
            warn("Time is too close to the last data point", secondsToSleep=diff)
            sleepWithProgressBar(diff)

    except Exception:
        data = []
        warn("Cannot find previous file; creating new", filename=filename)

    token0 = POOL_INFO[name]["token0"]
    token1 = POOL_INFO[name]["token1"]

    prices = cg.get_price(
        ids= token0["id"] + "," + token1["id"],
        vs_currencies="usd"
    )
    info(
        "Fetched prices",
        token0=prices[token0["id"]]["usd"],
        token1=prices[token1["id"]]["usd"]
    )

    token0Reserve, token1Reserve, _ = pool.functions.getReserves().call()
    token0Reserve /= 10 ** token0["decimals"]
    token1Reserve /= 10 ** token1["decimals"]
    info(
        "Fetched reserves",
        token0Reserve=token0Reserve,
        token1Reserve=token1Reserve
    )

    totalSupply = pool.functions.totalSupply().call()
    userShare = pool.functions.balanceOf(USER).call()
    info(
        "Fetched user data",
        userShare=userShare,
        totalSupply=totalSupply,
        userPercentageShare="{:.2f}%".format(userShare / totalSupply * 100)
    )

    data.append({
        "timestamp": int(time.time()),
        "token0Balance": token0Reserve * userShare / totalSupply,
        "token1Balance": token0Reserve * userShare / totalSupply,
        "token0Price": prices[token0["id"]]["usd"],
        "token1Price": prices[token1["id"]]["usd"]
    })
    data = pd.DataFrame(data)
    data.to_csv(filename, index=False)
    info("Pool data saved", filename=filename)


while True:
    for name, pool in pools.items():
        fetchData(name, pool)
    sleepWithProgressBar(INTERVAL)
