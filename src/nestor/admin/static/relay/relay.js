// Forward the browser to the Nestor instance encoded in the OAuth `state`: "<state>.<base64url(callback URL)>".
(function () {
  "use strict";
  var message = document.getElementById("message");
  var params = new URLSearchParams(window.location.search);
  var state = params.get("state") || "";
  var dot = state.indexOf(".");
  try {
    if (dot < 0) throw new Error("no instance in state");
    var encoded = state.slice(dot + 1).replace(/-/g, "+").replace(/_/g, "/");
    var target = new URL(atob(encoded + "===".slice(0, (4 - (encoded.length % 4)) % 4)));
    if ((target.protocol !== "http:" && target.protocol !== "https:") || !/\/connections\/callback$/.test(target.pathname)) {
      throw new Error("not a Nestor callback");
    }
    target.search = window.location.search;
    window.location.replace(target.toString());
  } catch (error) {
    message.textContent = "Ce lien ne mène à aucune instance Nestor : recommencez la connexion depuis l'administration.";
  }
})();
