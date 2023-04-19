/**
 JQuery Autocomplete and supporting functions.
 */
$(function () {
    $("#pepe-input-text-box").autocomplete({
        source: function (request, response) {
            var results = $.ui.autocomplete.filter(pepe_names, request.term);
            response(results.slice(0, 15))
        }
    });
});


function verify_pepe(pepe_name, pepe_list) {
    if (!(pepe_list.includes(pepe_name))) {
        errorTarget = document.getElementById('invalid_pepe');
        errorTarget.textContent = pepe_name + " is not a rare pepe name. Please re-enter the name.";
        return false;
    } else {
        tagTarget = document.getElementsByName('checkoutDesc')[0];
        tagTarget.value = tagTarget.value.replace('_PEPE_NAME_', get_typed_pepe());
        input_box_select();
        return true;
    }
}

function get_typed_pepe() {
    typed_pepe = document.getElementById('pepe-input-text-box')['value'];
    return typed_pepe;
}

$(document).ready(function () {
    $("#pepe-input-text-box").click(function () {
        $("#pepe-input-text-box").select();
    });
});

$(document).ready(function(e) {
    var $input = $('#refresh');

    $input.val() == 'yes' ? location.reload(true) : $input.val('yes');
});
