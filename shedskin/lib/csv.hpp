/* Copyright 2005-2011 Mark Dufour and contributors; License Expat (See LICENSE) */

#ifndef __CSV_HPP
#define __CSV_HPP

#include "builtin.hpp"

using namespace __shedskin__;
namespace __csv__ {

extern tuple2<str *, str *> *const_3;
extern list<void *> *const_0;
extern str *const_1, *const_10, *const_11, *const_12, *const_13, *const_14, *const_15, *const_16, *const_17, *const_18, *const_19, *const_2, *const_20, *const_21, *const_22, *const_23, *const_24, *const_25, *const_26, *const_27, *const_4, *const_5, *const_6, *const_7, *const_8, *const_9;

class Error;
class Excel;
class reader;
class writer;
class DictReader;
class DictWriter;

extern str *__name__;
extern __ss_int EAT_CRNL, ESCAPED_CHAR, ESCAPE_IN_QUOTED_FIELD, IN_FIELD, IN_QUOTED_FIELD, QUOTE_ALL, QUOTE_IN_QUOTED_FIELD, QUOTE_MINIMAL, QUOTE_NONE, QUOTE_NONNUMERIC, START_FIELD, START_RECORD, _field_limit;
extern OSError *__exception;

extern class_ *cl_Error;
class Error : public Exception {
public:

    Error() {}
    Error(str *msg) {
        this->__class__ = cl_Error;
        __init__(msg);
    }
};

extern class_ *cl_Excel;
class Excel : public pyobj {
public:
    str *lineterminator;
    __ss_int skipinitialspace;
    __ss_int quoting;
    __ss_int strict;
    str *delimiter;
    str *escapechar;
    str *quotechar;
    __ss_int doublequote;

    Excel() {}
    Excel(__ss_int) {
        this->__class__ = cl_Excel;
        __init__();
    }
    void *__init__();
};

class __csviter : public __iter<list<str *> *> {
public:
    reader *r;
    __csviter(reader *r_);
    list<str *> *__next__();
};

extern class_ *cl_reader;
class reader : public pyiter<list<str *> *> {
public:
    Excel *dialect;
    __ss_int line_num;
    list<str *> *fields;
    list<str *> *field;
    __ss_int state;
    __ss_int numeric_field;
    file *input_iter;

    reader() {}
    reader(file *input_iter_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict) {
        this->__class__ = cl_reader;
        __init__(input_iter_, dialect_, delimiter, quotechar, doublequote, skipinitialspace, lineterminator, quoting, escapechar, strict);
    }
    void *parse_process_char(str *c);
    void *parse_reset();
    list<str *> *__next__();
    __csviter *__iter__();
    void *__init__(file *input_iter_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict);
    void *parse_save_field();
    void *parse_add_char(str *c);
};

extern class_ *cl_writer;
class writer : public pyobj {
public:
    Excel *dialect;
    __ss_int num_fields;
    file *output_file;
    list<str *> *rec;

    writer() {}
    writer(file *output_file_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict) {
        this->__class__ = cl_writer;
        __init__(output_file_, dialect_, delimiter, quotechar, doublequote, skipinitialspace, lineterminator, quoting, escapechar, strict);
    }
    __ss_int join_append_data(str *field, __ss_int quote_empty, __ss_int quoted);
    void *writerow(list<str *> *seq);
    void *join_reset();
    void *writerows(list<list<str *> *> *seqs);
    __ss_int join_append(str *field, __ss_int quoted, __ss_int quote_empty);
    void *__init__(file *output_file_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict);
};

class __driter : public __iter<dict<str *, str *> *> {
public:
    DictReader *r;
    __driter(DictReader *r_);
    dict<str *, str *> *__next__();
};

extern class_ *cl_DictReader;
class DictReader : public pyiter<dict<str *, str *> *> {
public:
    str *restval;
    str *dialect;
    __ss_int line_num;
    str *restkey;
    list<str *> *_fieldnames;
    reader *_reader;

    DictReader() {}
    DictReader(file *f, list<str *> *fieldnames_, str *restkey_, str *restval_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict) {
        this->__class__ = cl_DictReader;
        __init__(f, fieldnames_, restkey_, restval_, dialect_, delimiter, quotechar, doublequote, skipinitialspace, lineterminator, quoting, escapechar, strict);
    }
    void *setfieldnames(list<str *> *value);
    dict<str *, str *> *__next__();
    __driter *__iter__();
    list<str *> *getfieldnames();
    void *__init__(file *f, list<str *> *fieldnames_, str *restkey_, str *restval_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict);
};

extern class_ *cl_DictWriter;
class DictWriter : public pyobj {
public:
    str *restval;
    writer *_writer;
    list<str *> *fieldnames;
    str *extrasaction;

    DictWriter() {}
    DictWriter(file *f, list<str *> *fieldnames_, str *restval_, str *extrasaction_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict) {
        this->__class__ = cl_DictWriter;
        __init__(f, fieldnames_, restval_, extrasaction_, dialect_, delimiter, quotechar, doublequote, skipinitialspace, lineterminator, quoting, escapechar, strict);
    }
    list<str *> *_dict_to_list(dict<str *, str *> *rowdict);
    void *writerow(dict<str *, str *> *rowdict);
    void *writerows(list<dict<str *, str *> *> *rowdicts);
    void *__init__(file *f, list<str *> *fieldnames_, str *restval_, str *extrasaction_, str *dialect_, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict);
};

extern void * default_9;
extern void * default_14;
extern void * default_16;
extern void * default_21;
extern void * default_23;
extern str * default_18;
extern void * default_25;
extern void * default_0;
extern void * default_2;
extern void * default_6;
extern void * default_3;
extern void * default_8;
extern void * default_10;
extern void * default_11;
extern void * default_13;
extern void * default_15;
extern void * default_12;
extern void * default_17;
extern void * default_24;
extern str * default_19;
extern str * default_20;
extern void * default_22;
extern void * default_7;
extern void * default_1;
extern void * default_5;
extern void * default_4;

void __init();
list<str *> *list_dialects();
Excel *_get_dialect(str *name, str *delimiter, str *quotechar, __ss_int doublequote, __ss_int skipinitialspace, str *lineterminator, __ss_int quoting, str *escapechar, __ss_int strict);
__ss_int field_size_limit(__ss_int new_limit);

} // module namespace
#endif
