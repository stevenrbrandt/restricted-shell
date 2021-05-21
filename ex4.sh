export b="u v\""
export c='s t'
for q in $c ${b}
do
for p in x y
do echo $q $p
done
done
