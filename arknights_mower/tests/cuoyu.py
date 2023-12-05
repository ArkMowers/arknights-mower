class Calculator:
    def __init__(self):
        self.input_日_钱_基建内_永远上班 = 50000
        self.input_日_钱_基建内_暂时上班 = 30000
        self.input_日_书_基建内 = 16500
        self.input_预设土量 = 16000
        self.input_搓玉人_效率和 = 2.1505
        self.input_卖玉人_效率和 = 3
        self.input_目标练度钱 = 761409
        self.input_目标练度书 = 588286
        self.目标练度钱书比 = self.input_目标练度钱 / self.input_目标练度书
        self.练度列表 = []
        self.练度列表_离谱 = []
        self.日_钱_基建外 = 43482.63
        self.日_书_基建外 = 36284.48

    def 搓玉天数(self, 土量):
        return int(土量 / 2 / 24 / self.input_搓玉人_效率和) + 1

    def 搓玉用钱(self, 土量):
        return 土量 * 800

    def 卖玉天数(self, 土量):
        return int(土量 / 2 / 2 / 24 * 2 / self.input_卖玉人_效率和) + 1

    def calculate(self):
        from itertools import product as 多循环

        for 土量, 日_钱_基建内_永远上班, 日_书_基建内 in 多循环(
            range(self.input_预设土量, 25000, 80),
            range(self.input_日_钱_基建内_永远上班, 60000, 1000),
            range(self.input_日_书_基建内, 20000, 1000),
        ):
            # 钱
            搓玉所需钱数 = self.搓玉用钱(土量)
            卖玉天数 = self.卖玉天数(土量)
            基建内_年产钱 = 日_钱_基建内_永远上班 * 365 + self.input_日_钱_基建内_暂时上班 * (365 - 卖玉天数)
            总_年产钱 = 基建内_年产钱 + self.日_钱_基建外 * 365 - 搓玉所需钱数
            # 书
            搓玉天数 = self.搓玉天数(土量)
            总_年产书 = 日_书_基建内 * (365 - 搓玉天数) + self.日_书_基建外 * 365
            总_日产钱 = 总_年产钱 / 365
            总_日产书 = 总_年产书 / 365
            # 最终计算
            日_钱书总数 = 日_钱_基建内_永远上班 + self.input_日_钱_基建内_暂时上班 + 日_书_基建内
            总_钱书比 = round(总_日产钱 / 总_日产书, 2)
            总_能练干员 = int(min(总_年产钱 / self.input_目标练度钱, 总_年产书, self.input_目标练度书))
            日_钱_基建内 = int(日_钱_基建内_永远上班 + self.input_日_钱_基建内_暂时上班)
            日销售记录 = [日_钱_基建内, 日_书_基建内, 总_钱书比, 总_能练干员, 搓玉天数, 卖玉天数, 土量, 土量 * 5]
            for i in 日销售记录:
                if i < 0:
                    print("出错了")
            self.练度列表_离谱.append(日销售记录)
            if 日_钱书总数 < 100000 and abs(总_钱书比 - self.目标练度钱书比) < 0.005:
                self.练度列表.append(日销售记录)

        a = "日_钱_基建内, 日_书_基建内, 总_钱书比, 总_能练干员, 搓玉天数, 卖玉天数, 土量, 土量 * 5"
        list2 = a.split(", ")

        try:
            self.练度列表排序 = sorted(self.练度列表, key=lambda x: x[-1])
            for val1, val2 in zip(list2, self.练度列表排序[0]):
                print(f"{val1}: {val2}")

        except:
            print("出问题了")
            练度列表排序 = sorted(self.练度列表_离谱, key=lambda x: x[0])
            for val1, val2 in zip(list2, 练度列表排序[0]):
                print(f"{val1}: {val2}")


# Create an instance of the Calculator class
calc = Calculator()
calc.calculate()  # Perform calculations using the defined method
