for i in 1 2 3 4 5 6 7
do
    bash ex${i}.sh x y z> x1
    python3 ./shell2.py ex${i}.sh > x2
    diff x1 x2 > /dev/null
    if [ "$?" != 0 ]
    then
        echo "Failure for test: ex${i}.sh"
        exit 2
    fi
done
