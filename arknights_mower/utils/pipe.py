def push_operators(func):
    def func_dec(s,*args):
        r=func(s,*args)
        if Pipe is not None and Pipe.conn is not None:
            # print('发送数据')
            # print(s.op_data.operators)
            Pipe.conn.send({'type':'operators','data':s.op_data.operators})
        return r
    return func_dec


class Pipe:
    conn = None


