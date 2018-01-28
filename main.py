#! /usr/bin/env python3
import re
import asyncio
from decimal import Decimal

from async_gui.engine import Task
from async_gui.toolkits.kivy import KivyEngine
engine = KivyEngine()

import kivy
kivy.require("1.10.0")

from kivy.utils import platform
from kivy.core.window import Window
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty, ObjectProperty
from kivy.uix.screenmanager import Screen

from kivymd.theming import ThemeManager
from kivymd.list import TwoLineIconListItem
from kivymd.list import ILeftBodyTouch
from kivymd.button import MDIconButton
from kivymd.dialog import MDDialog
from kivymd.label import MDLabel
from kivymd.textfields import MDTextField

import nowallet
#from nowallet.exchange_rate import fetch_exchange_rates
from settings_json import settings_json

__version__ = nowallet.__version__
if platform != "android":
    Window.size = (350, 550)

# Declare screens
class LoginScreen(Screen):
    pass

class MainScreen(Screen):
    pass

class WaitScreen(Screen):
    pass

class YPUBScreen(Screen):
    pass

class IconLeftSampleWidget(ILeftBodyTouch, MDIconButton):
    pass

class ListItem(TwoLineIconListItem):
    history = ObjectProperty(object())
    def on_release(self):
        txid = self.history.tx_obj.id()
        chain = app.chain.chain_1209k
        chain = "btc-testnet" if chain == "tbtc" else chain
        url = "https://live.blockcypher.com/{}/tx/{}/".format(chain, txid)
        open_url(url)

class FloatInput(MDTextField):
    pat = re.compile('[^0-9]')
    def insert_text(self, substring, from_undo=False):
        pat = self.pat
        if '.' in self.text:
            s = re.sub(pat, '', substring)
        else:
            s = '.'.join([re.sub(pat, '', s) for s in substring.split('.', 1)])
        return super(FloatInput, self).insert_text(s, from_undo=from_undo)

class NowalletApp(App):
    theme_cls = ThemeManager()
    theme_cls.theme_style = "Dark"
    theme_cls.primary_palette = "Grey"
    theme_cls.accent_palette = "LightGreen"

    units = StringProperty()
    currency = StringProperty()
    current_coin = StringProperty("0")
    current_fiat = StringProperty("0")
    current_fee = NumericProperty()

    def __init__(self):
        self.chain = nowallet.TBTC
        self.loop = asyncio.get_event_loop()
        self.is_amount_inputs_locked = False

        self.menu_items = [{"viewclass": "MDMenuItem",
                            "text": "View YPUB"},
#                           {"viewclass": "MDMenuItem",
#                            "text": "Lock with PIN"},
                           {"viewclass": "MDMenuItem",
                            "text": "Settings"}]
        super().__init__()

    def show_dialog(self, title, message):
        content = MDLabel(font_style='Body1',
                          theme_text_color='Secondary',
                          text=message,
                          size_hint_y=None,
                          valign='top')
        content.bind(texture_size=content.setter('size'))
        self.dialog = MDDialog(title=title,
                               content=content,
                               size_hint=(.8, None),
                               height=dp(200),
                               auto_dismiss=False)

        self.dialog.add_action_button("Dismiss",
                                      action=lambda *x: self.dialog.dismiss())
        self.dialog.open()

    def menu_item_handler(self, text):
        if self.root.ids.sm.current == "main":
            if "YPUB" in text:
                self.root.ids.sm.current = "ypub"
#            elif "PIN" in text:
#                pass
            elif "Settings" in text:
                self.open_settings()

    def fee_button_handler(self):
        fee_input = self.root.ids.fee_input
        fee_button = self.root.ids.fee_button
        fee_input.disabled = not fee_input.disabled
        if not fee_input.disabled:
            fee_button.text = "Custom Fee"
        else:
            fee_button.text = "Normal Fee"
            fee_input.text = str(self.estimated_fee)
            self.current_fee = self.estimated_fee

    def fee_input_handler(self):
        text = self.root.ids.fee_input.text
        if text:
            self.current_fee = int(float(text))

    def check_new_history(self, dt):
        if self.wallet.new_history:
            self.update_screens()
            self.wallet.new_history = False

    def do_login(self):
        email = self.root.ids.email_field.text
        passphrase = self.root.ids.pass_field.text
        confirm = self.root.ids.confirm_field.text
        if not email or not passphrase or not confirm:
            self.show_dialog("Error", "All fields are required.")
            return
        if passphrase != confirm:
            self.show_dialog("Error", "Passwords did not match.")
            return
        bech32 = self.root.ids.bech32_checkbox.active
        if bech32: self.menu_items[0]["text"] = "View ZPUB"

        self.root.ids.sm.current = "wait"
        self.do_login_tasks(email, passphrase, bech32)
        self.update_screens()
        self.root.ids.sm.current = "main"
        Clock.schedule_interval(self.check_new_history, 1)

    @engine.async
    def do_login_tasks(self, email, passphrase, bech32):
        self.root.ids.wait_text.text = "Connecting.."
        server, port, proto = yield Task(
            nowallet.get_random_onion, self.loop, self.chain)
        connection = yield Task(
            nowallet.Connection, self.loop, server, port, proto)
#        connection = yield Task(
#            nowallet.Connection, self.loop, "mdw.ddns.net", 50002, "s")
        self.root.ids.wait_text.text = "Deriving Keys.."
        self.wallet = yield Task(
            nowallet.Wallet, email, passphrase,
            connection, self.loop, self.chain)
        self.wallet.bech32 = bech32
        self.root.ids.wait_text.text = "Fetching history.."
        yield Task(self.wallet.discover_all_keys)
        self.root.ids.wait_text.text = "Fetching exchange rates.."
        self.exchange_rates = {"USD": 12000.0}
#        self.exchange_rates = yield Task(self.loop.run_until_complete,
#            fetch_exchange_rates(self.chain.chain_1209k))
        self.root.ids.wait_text.text = "Getting fee estimate.."
        coinkb_fee = yield Task(self.wallet.get_fee_estimation)
        self.current_fee = self.estimated_fee = \
            nowallet.Wallet.coinkb_to_satb(coinkb_fee)

    def update_screens(self):
        self.update_balance_screen()
        self.update_send_screen()
        self.update_recieve_screen()
        self.update_ypub_screen()

    def balance_str(self):
        balance = self.unit_precision.format(
            self.wallet.balance * self.unit_factor)
        return "{} {}".format(balance.rstrip("0").rstrip("."), self.units)

    def update_balance_screen(self):
        self.root.ids.balance_label.text = self.balance_str()
        self.root.ids.recycleView.data_model.data = []
        for hist in self.wallet.get_tx_history():
            verb = "Sent" if hist.is_spend else "Recieved"
            hist_str = "{} {} {}".format(
                verb, hist.value * self.unit_factor, self.units)
            self.add_list_item(hist_str, hist)

    def update_send_screen(self):
        self.root.ids.send_balance.text = \
            "Available balance:\n" + self.balance_str()
        self.root.ids.fee_input.text = str(self.current_fee)

    def update_recieve_screen(self):
        address = self.update_recieve_qrcode()
        encoding = "bech32" if self.wallet.bech32 else "P2SH"
        self.root.ids.addr_label.text = \
            "Current Address ({}):\n{}".format(encoding, address)

    def update_recieve_qrcode(self):
        address = self.wallet.get_address(self.wallet.get_next_unused_key())
        amount = Decimal(self.current_coin) / self.unit_factor
        self.root.ids.addr_qrcode.data = \
            "bitcoin:{}?amount={}".format(address, amount)
        return address

    def update_ypub_screen(self):
        ypub = self.wallet.ypub
        if self.wallet.bech32: ypub[0] = "z"
        self.root.ids.ypub_label.text = "Extended Public Key (SegWit):\n" + ypub
        self.root.ids.ypub_qrcode.data = ypub

    def update_unit(self):
        self.unit_factor = 1
        self.unit_precision = "{:.8f}"
        if self.units[0] == "m":
            self.unit_factor = 1000
            self.unit_precision = "{:.5f}"
        elif self.units[0] == "u":
            self.unit_factor = 1000000
            self.unit_precision = "{:.2f}"

        self.current_coin = str( Decimal(self.current_coin) / self.unit_factor )
        self.current_fiat = str( Decimal(self.current_fiat) / self.unit_factor )

    def update_amounts(self, text=None, type="coin"):
        if self.is_amount_inputs_locked: return
        amount = Decimal(text) if text else Decimal("0")
        rate = self.exchange_rates[self.currency] if self.exchange_rates else 1
        rate = Decimal(str(rate)) / self.unit_factor
        new_amount = None
        if type == "coin":
            new_amount = amount * rate
            self.update_amount_fields(amount, new_amount)
        elif type == "fiat":
            new_amount = amount / rate
            self.update_amount_fields(new_amount, amount)
        self.update_recieve_qrcode()

    def update_amount_fields(self, coin, fiat):
        self.is_amount_inputs_locked = True
        _coin = self.unit_precision.format(coin)
        self.current_coin = _coin.rstrip("0").rstrip(".")
        _fiat = "{:.2f}".format(fiat)
        self.current_fiat = _fiat.rstrip("0").rstrip(".")
        self.is_amount_inputs_locked = False

    def build(self):
        self.icon = "icons/brain.png"
        self.use_kivy_settings = False
        self.rbf = self.config.get("nowallet", "rbf")
        self.units = self.config.get("nowallet", "units")
        self.update_unit()
        self.currency = self.config.get("nowallet", "currency")

    def build_config(self, config):
        config.setdefaults("nowallet", {
            "rbf": False,
            "units": self.chain.chain_1209k.upper(),
            "currency": "USD"})
        Window.bind(on_keyboard=self.key_input)

    def build_settings(self, settings):
        coin = self.chain.chain_1209k.upper()
        settings.add_json_panel("Nowallet Settings",
                                self.config,
                                data=settings_json(coin))

    def on_config_change(self, config, section, key, value):
        if key == "rbf":
            self.rbf = value
        elif key == "units":
            self.units = value
            self.update_unit()
            self.update_amounts()
            self.update_balance_screen()
            self.update_send_screen()
        elif key == "currency":
            self.currency = value
            self.update_amounts()

    def key_input(self, window, key, scancode, codepoint, modifier):
        if key == 27:   # the back button / ESC
            return True  # override the default behaviour
        else:           # the key now does nothing
            return False

    def on_pause(self):
        return True

    def add_list_item(self, text, history):
        data = self.root.ids.recycleView.data_model.data
        data.insert(0, {"text": text,
                        "secondary_text": history.tx_obj.id(),
                        "history": history})

if platform == "android":
    from jnius import autoclass, cast
    context = autoclass('org.renpy.android.PythonActivity').mActivity
    Uri = autoclass('android.net.Uri')
    Intent = autoclass('android.content.Intent')

def open_url(url):
    if platform == "android":
        ''' Open a webpage in the default Android browser.  '''
        intent = Intent()
        intent.setAction(Intent.ACTION_VIEW)
        intent.setData(Uri.parse(url))
        currentActivity = cast('android.app.Activity', context)
        currentActivity.startActivity(intent)
    else:
        import webbrowser
        webbrowser.open(url)

if __name__ == "__main__":
    app = NowalletApp()
    engine.main_app = app
    app.run()
