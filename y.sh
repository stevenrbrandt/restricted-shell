#!/home/sbrandt/py/shell/shell.py
sh -c ./a.sh
echo "A=$?"
sh -c ./b.sh
echo "B=$?"
if sh -c ./a.sh && sh -c ./b.sh
then
    echo A and B
fi
echo '==='
if sh -c ./b.sh && sh -c ./a.sh
then
    echo B and A
fi
echo '==='
echo "HERE"
if sh -c ./a.sh || sh -c ./b.sh
then
    echo A or B
fi
echo '==='
if sh -c ./b.sh && sh -c ./b.sh
then
    echo B and B
fi
