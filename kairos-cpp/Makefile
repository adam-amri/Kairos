# Repli sans CMake : make suffit.
#
# -ffast-math est volontairement ABSENT. Il autorise le reordonnancement des
# operations flottantes et suppose l'absence de NaN : le determinisme du moteur
# en depend, et c'est lui qui rend possible le test de non-regression
# backtest/live ainsi que l'analyse d'incident.

CXX      ?= g++
CXXFLAGS := -std=c++20 -O3 -Wall -Wextra -Wpedantic -Wno-psabi -Iinclude
BIN      := bin

.PHONY: all test arb bench xval clean

all: $(BIN)/tests $(BIN)/test_arb $(BIN)/bench $(BIN)/crossvalidate

$(BIN):
	@mkdir -p $(BIN)

$(BIN)/tests: tests/test_main.cpp tests/reference_values.hpp | $(BIN)
	$(CXX) $(CXXFLAGS) -Itests $< -o $@

$(BIN)/test_arb: tests/test_arb.cpp include/kairos/arb/detector.hpp | $(BIN)
	$(CXX) $(CXXFLAGS) $< -o $@

$(BIN)/bench: bench/bench_main.cpp | $(BIN)
	$(CXX) $(CXXFLAGS) -march=native $< -o $@

$(BIN)/crossvalidate: apps/crossvalidate.cpp | $(BIN)
	$(CXX) $(CXXFLAGS) $< -o $@

test: $(BIN)/tests $(BIN)/test_arb
	@./$(BIN)/tests
	@echo
	@./$(BIN)/test_arb

bench: $(BIN)/bench
	@./$(BIN)/bench 1000000

xval: $(BIN)/crossvalidate
	@./$(BIN)/crossvalidate

clean:
	@rm -rf $(BIN)

arb: $(BIN)/test_arb
	@./$(BIN)/test_arb
