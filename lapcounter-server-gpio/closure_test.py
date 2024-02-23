

globalvar = "i am global"

def closure_test():
    def inner():
        innervar = "i am inner"
        print(localvar)
        print(globalvar)    
    localvar = "i am local"

    inner()

closure_test()


