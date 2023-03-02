import tkinter
from tkinter import messagebox, TclError


def message_box_action(yes_action=lambda: print('Yes action'),
                       no_action=lambda: print('No action'),
                       message='Do?',
                       timeout=3000,
                       default=True):
    root = tkinter.Tk()
    root.withdraw()
    root.after(timeout, root.destroy)

    answer = default
    try:
        answer = messagebox.askyesno(
            '', f"{message} (timeout: {timeout}, default: {default})")

    except TclError:
        pass

    if answer:
        yes_action()
    else:
        no_action()


if __name__ == '__main__':
    message_box_action(lambda: print('fff'))
    print('fff')
