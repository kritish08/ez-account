import re

with open("src/pages/Products.js", "r") as f:
    code = f.read()

# Generate RawMaterials.js
raw_code = code.replace("const Products = ()", "const RawMaterials = ()")
raw_code = raw_code.replace("export default Products", "export default RawMaterials")
raw_code = raw_code.replace(">Products<", ">Raw Materials<")
raw_code = raw_code.replace('Manage your product catalog, prices, and stock levels', 'Manage procurement, raw materials, and stock levels')
raw_code = raw_code.replace("getProducts()", "getProducts({ item_type: 'raw_material,wip' })")
# Hardcode item_type in default form data for RawMaterials
raw_code = re.sub(r'item_type:\s*"finished_good"', 'item_type: "raw_material"', raw_code)
# Remove the item_type dropdown entirely because we are forcing it? 
# Actually, just leave the dropdown but let the user select raw_material or wip.

with open("src/pages/RawMaterials.js", "w") as f:
    f.write(raw_code)

# Generate FinishedGoods.js
fg_code = code.replace("const Products = ()", "const FinishedGoods = ()")
fg_code = fg_code.replace("export default Products", "export default FinishedGoods")
fg_code = fg_code.replace(">Products<", ">Finished Goods<")
fg_code = fg_code.replace('Manage your product catalog, prices, and stock levels', 'Manage final sellable goods and price margins')
fg_code = fg_code.replace("getProducts()", "getProducts({ item_type: 'finished_good' })")

with open("src/pages/FinishedGoods.js", "w") as f:
    f.write(fg_code)

