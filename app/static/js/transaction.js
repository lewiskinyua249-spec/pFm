
document.addEventListener("DOMContentLoaded", function () {

    const typeSelect = document.getElementById("type");
    const categorySelect = document.getElementById("category_id");

    if (!typeSelect || !categorySelect) {
        return;
    }

    function filterCategories() {

        const selectedType = typeSelect.value;

        Array.from(categorySelect.options).forEach(function (option) {

            const categoryType = option.dataset.type;

            // Keep the default "No category" option visible.
            if (!categoryType) {
                option.hidden = false;
                return;
            }

            // Show only categories matching the transaction type.
            option.hidden = (
                selectedType !== "" &&
                categoryType !== selectedType
            );
        });

        // Clear a category that no longer matches.
        const selectedOption =
            categorySelect.options[categorySelect.selectedIndex];

        if (
            selectedOption &&
            selectedOption.dataset.type &&
            selectedOption.dataset.type !== selectedType
        ) {
            categorySelect.value = "";
        }
    }

    typeSelect.addEventListener("change", filterCategories);

    filterCategories();

});
