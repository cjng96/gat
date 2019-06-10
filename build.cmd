python3 setup.py bdist_wheel
bash --login -c "printf 'cjng96\n' | twine upload dist/*"
pause
