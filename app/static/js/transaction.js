
document.addEventListener("DOMContentLoaded", function () {

    const typeSelect = document.getElementById("type");
    const categorySelect = document.getElementById("category_id");
    const newCategoryField = document.getElementById("new-category-field");
    const newCategoryName = document.getElementById("new_category_name");

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

        updateNewCategoryField();
    }

    function updateNewCategoryField() {
        if (!newCategoryField || !newCategoryName) {
            return;
        }

        const creatingCategory = categorySelect.value === "new";
        newCategoryField.hidden = !creatingCategory;
        newCategoryName.disabled = !creatingCategory;
        newCategoryName.required = creatingCategory;

        if (!creatingCategory) {
            newCategoryName.value = "";
        }
    }

    typeSelect.addEventListener("change", filterCategories);
    categorySelect.addEventListener("change", updateNewCategoryField);

    filterCategories();

});
