/* Copyright 2005-2022 Mark Dufour and contributors; License Expat (See LICENSE) */

/* bytes methods TODO share code with str */

bytes::bytes(int frozen) : hash(-1), frozen(frozen) {
    __class__ = cl_bytes;
}

bytes::bytes(const char *s) : unit(s), hash(-1) {
    __class__ = cl_bytes;
}

bytes::bytes(__GC_STRING s) : unit(s), hash(-1) {
    __class__ = cl_bytes;
}

bytes::bytes(bytes *b, int frozen) : hash(-1), frozen(frozen) {
    __class__ = cl_bytes;
    unit = b->unit;
}

bytes::bytes(const char *s, int size) : unit(s, size), hash(-1) { /* '\0' delimiter in C */
    __class__ = cl_bytes;
}

const char *bytes::c_str() const {
    return this->unit.c_str();
}

const int bytes::size() const {
    return this->unit.size();
}

str *bytes::__str__() {
    if(frozen)
        return __add_strs(3, new str("bytearray(b'"), new str(this->unit), new str("')"));
    else
        return __add_strs(3, new str("b'"), new str(this->unit), new str("'"));
}

const int bytes::find(const char c, int a) const {
    return this->unit.find(c, a);
}

const int bytes::find(const char *c, int a) const {
    return this->unit.find(c, a);
}

str *bytes::__repr__() {
    std::stringstream ss;
    __GC_STRING sep = "\\\n\r\t";
    __GC_STRING let = "\\nrt";

    const char *quote = "'";
    int hasq = find('\'');
    int hasd = find('\"');

    if (hasq != -1 && hasd != -1) {
        sep += "'"; let += "'";
    }
    if (hasq != -1 && hasd == -1)
        quote = "\"";

    ss << 'b';
    ss << quote;
    for(unsigned int i=0; i<size(); i++)
    {
        char c = unit[i];
        int k;

        if((k = sep.find_first_of(c)) != -1)
            ss << "\\" << let[k];
        else {
            int j = (int)((unsigned char)c);

            if(j<16)
                ss << "\\x0" << std::hex << j;
            else if(j>=' ' && j<='~')
                ss << (char)j;
            else
                ss << "\\x" << std::hex << j;
        }
    }
    ss << quote;

    return new str(ss.str().c_str());
}

long bytes::__hash__() {
    if (hash != -1)
        return hash;

    hash = std::hash<std::string>{}(unit.c_str());

    return hash;
}

__ss_bool bytes::__eq__(pyobj *p) {
    bytes *q = (bytes *)p;
    size_t len = size();
    if(len != q->size() or (hash != -1 and q->hash != -1 and hash != q->hash))
        return False;
    return __mbool(memcmp(unit.data(), q->unit.data(), len) == 0);
}

bytes *bytes::__add__(bytes *b) {
    bytes *s = new bytes();

    s->unit.reserve(size()+b->size());
    s->unit.append(unit);
    s->unit.append(b->unit);

    return s;
}

bytes *bytes::__iadd__(bytes *b) {
    return __add__(b);
}