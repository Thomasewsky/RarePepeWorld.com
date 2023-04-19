function btc_price_clipboard() {
  var copyText = document.getElementById("dispenser_price_btc");
  copyText.select();
  copyText.setSelectionRange(0, 99999); /* For mobile devices */
  navigator.clipboard.writeText(copyText.value);
}
