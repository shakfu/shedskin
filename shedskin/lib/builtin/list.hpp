/* Copyright 2005-2024 Mark Dufour and contributors; License Expat (See LICENSE) */

#ifdef SS_DECL

template <class T> class list : public pyseq<T> {
public:
    __GC_VECTOR(T) units;

    list();
    template <class ... Args> list(int count, Args ... args);
    template <class U> list(U *iter);
    list(list<T> *p);
    list(tuple2<T, T> *p);
    list(str *s);

    void clear();
    void *__setitem__(__ss_int i, T e);
    void *__delitem__(__ss_int i);
    int empty();
    list<T> *__slice__(__ss_int x, __ss_int l, __ss_int u, __ss_int s);
    void *__setslice__(__ss_int x, __ss_int l, __ss_int u, __ss_int s, pyiter<T> *b);
    void *__setslice__(__ss_int x, __ss_int l, __ss_int u, __ss_int s, list<T> *b);
    void *__delete__(__ss_int i);
    void *__delete__(__ss_int x, __ss_int l, __ss_int u, __ss_int s);
    void *__delslice__(__ss_int a, __ss_int b);
    __ss_bool __contains__(T a);

    list<T> *__add__(list<T> *b);
    list<T> *__mul__(__ss_int b);

    template <class U> void *extend(U *iter);
    void *extend(list<T> *p);
    void *extend(tuple2<T,T> *p);
    void *extend(str *s);

    template <class U> list<T> *__iadd__(U *iter);
    list<T> *__imul__(__ss_int n);

    __ss_int index(T a);
    __ss_int index(T a, __ss_int s);
    __ss_int index(T a, __ss_int s, __ss_int e);

    __ss_int count(T a);
    str *__repr__();
    __ss_bool __eq__(pyobj *l);

    void resize(__ss_int i); /* XXX remove */

    inline T __getfast__(__ss_int i);
    inline T __getitem__(__ss_int i);
    inline __ss_int __len__();

    T pop();
    T pop(__ss_int m);
    void *remove(T e);
    template <class U> void *remove(U e);
    void *insert(__ss_int m, T e);

    void *append(T a);

    void *reverse();
    template<class U> void *sort(__ss_int (*cmp)(T, T), U (*key)(T), __ss_int reverse);
    template<class U> void *sort(__ss_int cmp, U (*key)(T), __ss_int reverse);
    void *sort(__ss_int (*cmp)(T, T), __ss_int key, __ss_int reverse);
    void *sort(__ss_int cmp, __ss_int key, __ss_int reverse);

    list<T> *__copy__();
    list<T> *__deepcopy__(dict<void *, pyobj *> *memo);

    /* iteration */

    inline bool for_in_has_next(size_t i);
    inline T for_in_next(size_t &i);
#ifdef __SS_BIND
    list(PyObject *);
    PyObject *__to_py__();
#endif
};

#else

#ifndef SS_LIST_HPP
#define SS_LIST_HPP

/* list methods */

template<class T> list<T>::list() {
    this->__class__ = cl_list;
}

template<class T> template <class ... Args> list<T>::list(int, Args ... args) {
    this->__class__ = cl_list;
    this->units = {(T)args...};
}

template<class T> template<class U> list<T>::list(U *iter) {
    this->__class__ = cl_list;
    typename U::for_in_unit e;
    typename U::for_in_loop __3;
    int __2;
    U *__1;
    FOR_IN(e,iter,1,2,3)
        this->units.push_back(e);
    END_FOR
}

template<class T> list<T>::list(list<T> *p) {
    this->__class__ = cl_list;
    this->units = p->units;
}

template<class T> list<T>::list(tuple2<T, T> *p) {
    this->__class__ = cl_list;
    this->units = p->units;
}

template<class T> list<T>::list(str *s) {
    this->__class__ = cl_list;
    this->units.resize(s->unit.size());
    size_t sz = s->unit.size();
    for(size_t i=0; i<sz; i++)
        this->units[i] = __char_cache[(unsigned char)s->unit[i]];
}

#ifdef __SS_BIND
template<class T> list<T>::list(PyObject *p) {
    if(!PyList_Check(p))
        throw new TypeError(new str("error in conversion to Shed Skin (list expected)"));

    this->__class__ = cl_list;
    size_t size = (size_t)PyList_Size(p);
    this->units.resize(size);
    for(size_t i=0; i<size; i++)
        this->units.at(i) = __to_ss<T>(PyList_GetItem(p, i));
}

template<class T> PyObject *list<T>::__to_py__() {
    int len = this->__len__();
    PyObject *p = PyList_New(len);
    for(int i=0; i<len; i++)
        PyList_SetItem(p, i, __to_py(this->__getitem__(i)));
    return p;
}
#endif

template<class T> void list<T>::clear() {
    units.resize(0);
}

template<class T> void list<T>::resize(__ss_int i) {
    units.resize(static_cast<size_t>(i));
}

template<class T> __ss_int list<T>::__len__() {
    return static_cast<__ss_int>(units.size());
}

template<class T> T list<T>::__getitem__(__ss_int i) {
    i = __wrap(this, i);
    return units[static_cast<size_t>(i)];
}

template<class T> __ss_bool list<T>::__eq__(pyobj *p) {
   auto *b = dynamic_cast<list<T> *>(p);
   if (!b) return False;
   size_t len = this->units.size();
   if(b->units.size() != len) return False;
   for(size_t i = 0; i < len; i++)
       if(!__eq(this->units[i], b->units[i]))
           return False;
   return True;
}

template<class T> void *list<T>::append(T a) {
    this->units.push_back(a);
    return NULL;
}

template<class T> template<class U> void *list<T>::extend(U *iter) {
    typename U::for_in_unit e;
    typename U::for_in_loop __3;
    int __2;
    U *__1;
    FOR_IN(e,iter,1,2,3)
        this->units.push_back(e);
    END_FOR
    return NULL;
}

template<class T> void *list<T>::extend(list<T> *p) {
    size_t l1, l2;
    l1 = this->units.size(); l2 = p->units.size();
    this->units.resize(l1+l2);
    memcpy(&(this->units[l1]), &(p->units[0]), sizeof(T)*l2);
    return NULL;
}
template<class T> void *list<T>::extend(tuple2<T,T> *p) {
    size_t l1, l2;
    l1 = this->units.size(); l2 = p->units.size();
    this->units.resize(l1+l2);
    memcpy(&(this->units[l1]), &(p->units[0]), sizeof(T)*l2);
    return NULL;
}

template<class T> void *list<T>::extend(str *s) {
    const size_t sz = s->unit.size();
    const size_t org_size = this->units.size();
    this->units.resize(sz+org_size);
    for(size_t i=0; i<sz; i++)
        this->units.at(i + org_size) = __char_cache[((unsigned char)(s->unit[i]))];
    return NULL;
}

template<class T> inline T list<T>::__getfast__(__ss_int i) {
    i = __wrap(this, i);
    return this->units[(size_t)i];
}

template<class T> void *list<T>::__setitem__(__ss_int i, T e) {
    i = __wrap(this, i);
    units[(size_t)i] = e;
    return NULL;
}

template<class T> void *list<T>::__delitem__(__ss_int i) {
    i = __wrap(this, i);
    units.erase(units.begin()+i);
    return NULL;
}

template<class T> int list<T>::empty() {
    return units.empty();
}

template<class T> list<T> *list<T>::__slice__(__ss_int x, __ss_int l, __ss_int u, __ss_int s) {
    list<T> *c = new list<T>();
    slicenr(x, l, u, s, this->__len__());
    if(s == 1) {
        c->units.resize((size_t)(u-l));
        memcpy(&(c->units[0]), &(this->units[(size_t)l]), sizeof(T)*((size_t)(u-l)));
    } else if(s > 0)
        for(__ss_int i=l; i<u; i += s)
            c->units.push_back(units[(size_t)i]);
    else
        for(__ss_int i=l; i>u; i += s)
            c->units.push_back(units[(size_t)i]);
    return c;
}

template<class T> void *list<T>::__setslice__(__ss_int x, __ss_int l, __ss_int u, __ss_int s, pyiter<T> *b) {
    list<T> *la = new list<T>(); /* XXX avoid intermediate list */
    typename pyiter<T>::for_in_unit e;
    typename pyiter<T>::for_in_loop __3;
    int __2;
    pyiter<T> *__1;
    FOR_IN(e,b,1,2,3)
        la->units.push_back(e);
    END_FOR
    this->__setslice__(x, l, u, s, la);
    return NULL;
}

template<class T> void *list<T>::__setslice__(__ss_int x, __ss_int l, __ss_int u, __ss_int s, list<T> *la) {
    slicenr(x, l, u, s, this->__len__());

    if(x&4 && s != 1) { // x&4: extended slice (step 's' is given), check if sizes match
        int slicesize;
        if(l == u) slicesize = 0; // XXX ugly
        else if(s > 0 && u < l) slicesize=0;
        else if(s < 0 && l < u) slicesize=0;
        else {
            int slicelen = __abs(u-l);
            int absstep = __abs(s);
            slicesize = slicelen/absstep;
            if(slicelen%absstep) slicesize += 1;
        }

        if(slicesize != len(la))
            throw new ValueError(__add_strs(0, new str("attempt to assign sequence of size "), __str(len(la)), new str(" to extended slice of size "), __str((__ss_int)slicesize)));
    }

    if(s == 1) {
        if(l <= u) {
            this->units.erase(this->units.begin()+l, this->units.begin()+u);
            this->units.insert(this->units.begin()+l, la->units.begin(), la->units.end());
        } else
            this->units.insert(this->units.begin()+l, la->units.begin(), la->units.end());
    }
    else {
        __ss_int i, j;
        if(s > 0)
            for(i = 0, j = l; j < u; i++, j += s)
                this->units[(size_t)j] = la->units[(size_t)i];
        else
            for(i = 0, j = l; j > u; i++, j += s)
                this->units[(size_t)j] = la->units[(size_t)i];
    }

    return NULL;
}

template<class T> void *list<T>::__delete__(__ss_int i) {
    i = __wrap(this, i);
    units.erase(units.begin()+i);
    return NULL;
}

template<class T> void *list<T>::__delete__(__ss_int x, __ss_int l, __ss_int u, __ss_int s) {
    slicenr(x, l, u, s, this->__len__());

    if(s == 1)
        __delslice__(l, u);
    else {
        __GC_VECTOR(T) v;
        for(__ss_int i=0; i<this->__len__();i++)
            if(i < l or i >= u or (i-l)%s)
                v.push_back(this->units[(size_t)i]);
        units = v;
    }
    return NULL;
}

template<class T> void *list<T>::__delslice__(__ss_int a, __ss_int b) {
    if(a>this->__len__()) return NULL;
    if(b>this->__len__()) b = this->__len__();
    units.erase(units.begin()+a,units.begin()+b);
    return NULL;
}

template<class T> __ss_bool list<T>::__contains__(T a) {
    size_t size = this->units.size();
    for(size_t i=0; i<size; i++)
        if(__eq(this->units[i], a))
            return True;
    return False;
}

template<class T> list<T> *list<T>::__add__(list<T> *b) {
    size_t l1 = this->units.size();
    size_t l2 = b->units.size();

    list<T> *c = new list<T>();
    c->units.resize(l1+l2);

    if(l1==1) c->units[0] = this->units[0];
    else memcpy(&(c->units[0]), &(this->units[0]), sizeof(T)*l1);
    if(l2==1) c->units[l1] = b->units[0];
    else memcpy(&(c->units[l1]), &(b->units[0]), sizeof(T)*l2);

    return c;
}

template<class T> list<T> *list<T>::__mul__(__ss_int b) {
    list<T> *c = new list<T>();
    if(b<=0) return c;
    size_t len = this->units.size();
    if(len==1)
        c->units.assign((size_t)b, this->units[0]);
    else {
        c->units.resize((size_t)b*len);
        for(size_t i=0; i<(size_t)b; i++)
            memcpy(&(c->units[i*len]), &(this->units[0]), sizeof(T)*len);
    }
    return c;
}

template<class T> template<class U> list<T> *list<T>::__iadd__(U *iter) {
    extend(iter);
    return this;
}

template<class T> list<T> *list<T>::__imul__(__ss_int n) {
    __ss_int l1 = this->__len__();
    this->units.resize(l1*n);
    for(__ss_int i = 1; i <= n-1; i++)
        memcpy(&(this->units[l1*i]), &(this->units[0]), sizeof(T)*l1);
    return this;
}

template<class T> __ss_int list<T>::index(T a) { return index(a, 0, this->__len__()); }
template<class T> __ss_int list<T>::index(T a, __ss_int s) { return index(a, s, this->__len__()); }
template<class T> __ss_int list<T>::index(T a, __ss_int s, __ss_int e) {
    __ss_int one = 1;
    slicenr(7, s, e, one, this->__len__());
    for(__ss_int i = s; i<e;i++)
        if(__eq(a,units[i]))
            return i;
    throw new ValueError(new str("list.index(x): x not in list"));
}

template<class T> __ss_int list<T>::count(T a) {
    __ss_int c = 0;
    __ss_int len = this->__len__();
    for(__ss_int i = 0; i<len;i++)
        if(__eq(a,units[i]))
            c++;
    return c;
}

template<class T> str *list<T>::__repr__() {
    str *r = new str("[");
    size_t len = this->units.size();
    for(size_t i=0; i<len; i++) {
        *r += repr(units[i])->c_str();
        if (i<len-1)
            *r += ", ";
    }
    *r += "]";
    return r;
}

template<class T> T list<T>::pop(__ss_int i) { /* XXX optimize */
    __ss_int len = this->__len__();
    if(len==0)
        throw new IndexError(new str("pop from empty list"));
    if(i<0) 
        i = len+i;
    if(i<0 or i>=len)
        throw new IndexError(new str("pop index out of range"));
    T e = units[(size_t)i];
    units.erase(units.begin()+i);
    return e;
}

template<class T> T list<T>::pop() {
    if(this->units.size()==0)
        throw new IndexError(new str("pop from empty list"));
    T e = units.back();
    units.pop_back();
    return e;
}

template<class T> void *list<T>::reverse() {
    std::reverse(this->units.begin(), this->units.end());
    return NULL;
}

template<class T> template <class U> void *list<T>::sort(__ss_int (*cmp)(T, T), U (*key)(T), __ss_int reverse) {
    if(key) {
        if(reverse)
            std::sort(units.begin(), units.end(), cpp_cmp_key_rev<T, U>(key));
        else
            std::sort(units.begin(), units.end(), cpp_cmp_key<T, U>(key));
    }
    else if(cmp) {
        if(reverse)
            std::sort(units.begin(), units.end(), cpp_cmp_custom_rev<T>(cmp));
        else
            std::sort(units.begin(), units.end(), cpp_cmp_custom<T>(cmp));
    } else {
        if(reverse)
            std::sort(units.begin(), units.end(), cpp_cmp_rev<T>);
        else
            std::sort(units.begin(), units.end(), cpp_cmp<T>);
    }

    return NULL;
}

template<class T> template <class U> void *list<T>::sort(__ss_int, U (*key)(T), __ss_int reverse) {
    return sort((__ss_int(*)(T,T))0, key, reverse);
}
template<class T> void *list<T>::sort(__ss_int (*cmp)(T, T), __ss_int, __ss_int reverse) {
    return sort(cmp, (__ss_int(*)(T))0, reverse);
}
template<class T> void *list<T>::sort(__ss_int, __ss_int, __ss_int reverse) {
    return sort((__ss_int(*)(T,T))0, (__ss_int(*)(T))0, reverse);
}

template<class T> void *list<T>::insert(__ss_int m, T e) {
    int len = this->__len__();
    if (m<0) m = len+m;
    if (m<0) m = 0;
    if (m>=len) m = len;
    units.insert(units.begin()+m, e);
    return NULL;
}

template<class T> void *list<T>::remove(T e) {
    __ss_int len = this->__len__();

    for(__ss_int i = 0; i < len; i++) {
        if(__eq(units[(size_t)i], e)) {
            units.erase(units.begin() + i);
            return NULL;
        }
    }

    throw new ValueError(new str("list.remove(x): x not in list"));
}
template<class T> template <class U> void *list<T>::remove(U) {
    throw new ValueError(new str("list.remove(x): x not in list"));
}

template<class T> inline bool list<T>::for_in_has_next(size_t i) {
    return i < units.size(); /* XXX opt end cond */
}

template<class T> inline T list<T>::for_in_next(size_t &i) {
    return units[i++];
}

template<class T, class U> list<T> *__add_list_elt(list<T> *l, U u) {
    list<T> *c = new list<T>();
    size_t ll = l->units.size();
    c->units.resize(ll+1);
    memcpy(&(c->units[0]), &(l->units[0]), sizeof(T)*ll);
    c->units[ll] = (T)u;
    return c;
}

#endif
#endif
