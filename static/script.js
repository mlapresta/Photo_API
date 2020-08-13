//Reference: https://stackoverflow.com/questions/37658524/copying-text-of-textarea-in-clipboard-when-button-is-clicked
function copyJWT() {

  document.querySelector("textarea").select();
  document.execCommand('copy');

}
