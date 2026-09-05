pragma circom 2.1.6;

include "node_modules/circomlib/circuits/comparators.circom";

template BudgetSufficiency(bits) {
    signal input privateBudget;
    signal input publicPrice;
    signal output sufficient;

    component belowPrice = LessThan(bits);
    belowPrice.in[0] <== privateBudget;
    belowPrice.in[1] <== publicPrice;
    sufficient <== 1 - belowPrice.out;
    sufficient === 1;
}

component main { public [publicPrice] } = BudgetSufficiency(32);
