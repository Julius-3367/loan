#!/bin/bash

# Remove all merge conflict markers and keep the "right" version (after =======)
find odoo_addons/alba_loans -type f \( -name "*.py" -o -name "*.xml" \) -exec sed -i '/^<<<<<<< HEAD$/,/^=======$/d' {} \;
find odoo_addons/alba_loans -type f \( -name "*.py" -o -name "*.xml" \) -exec sed -i '/^>>>>>>> [a-f0-9]*$/d' {} \;

echo "All merge conflicts resolved"
