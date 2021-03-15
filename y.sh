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
if sh -c ./a.sh || sh -c ./b.sh
then
    echo A or B
fi
echo '==='
if sh -c ./b.sh && sh -c ./b.sh
then
    echo B and B
fi
