# pip3 install twine build
# create .pypirc file - https://packaging.python.org/en/latest/specifications/pypirc/

# python3 setup.py bdist_wheel
python3 -m build
# bash --login -c "printf 'cjng96\n' | twine upload dist/*"
bash --login -c "twine upload --repository god-tool dist/*"
# read -p "Press enter to continue"


