#!/usr/bin/env python

import sys, requests, socket
import pyspark as ps
from pyspark import SparkConf,SparkContext
import pyspark.streaming as pss
from pyspark.sql import Row,SQLContext
import requests

IP = "000.000.0.00"
hashtags = []

def main():
    global hashtags
    global IP
    hashtags = ['#youtube', '#google', '#microsoft', '#amazon', '#oracle']
	
	# start connection
	# configure spark instance to default
    config = SparkConf()
    s_context = SparkContext(conf = config)
	# log error messages?
    s_context.setLogLevel("ERROR")

	# use spark context to create the stream context
	# interval size = 2 seconds
    s_stream_context = pss.StreamingContext(s_context, 2)
    s_stream_context.checkpoint("checkpoint_TSA")

	# connect to port 9009
    socket_ts = s_stream_context.socketTextStream("twitter", 9009)

	# word that are related to tweets
    words = socket_ts.flatMap(lambda line: line.split(" "))

    company_hashtags = words.filter(check_word)
	
	# map each hashtag (map reduce to count)
    hashtag_count = company_hashtags.map(lambda x: (x.lower(), 1))	

	# do the aggregation, note that now this is a sequence of RDDs
    hashtag_totals = hashtag_count.updateStateByKey(aggregate_tags_count)

	# set intervals
    hashtag_totals.foreachRDD(process_interval)

	#set up sql 
    sql_context = get_sql_context_instance(s_context)

	# start the streaming 
    s_stream_context.start()

    try:
		# wait for the streaming 
	    s_stream_context.awaitTermination()
    except KeyboardInterrupt:
        print("\nSpark shutting down\n")

# process a single time interval
def process_interval(time, rdd):
	# print a separator
	print("----------- %s -----------" % str(time))
	try:
		for tag in rdd.collect():
			sql_context = get_sql_context_instance(rdd.context)
			row_rdd = rdd.map(lambda w: Row(hashtag=w[0], hashtag_count=w[1]))
			hashtags_df = sql_context.createDataFrame(row_rdd)
			# dataframe as table
			hashtags_df.registerTempTable("hashtags")
			# print out all hashtags
			 
			hashtag_counts_df = sql_context.sql("select hashtag, hashtag_count from hashtags")
			hashtag_counts_df.show()
			send_df_to_dashboard(hashtag_counts_df)
	except:
		e = sys.exc_info()[0]
		print("Error: {}".format(e))

# adding the count of each hashtag
def aggregate_tags_count(new_values, total_sum):
	return sum(new_values) + (total_sum or 0)	

def check_word(text):
	for word in text.split(" "):
		if word.lower() in hashtags:
			return True
	return False

def get_sql_context_instance(spark_context):
	if ('sqlContextSingletonInstance' not in globals()):
		globals()['sqlContextSingletonInstance'] = SQLContext(spark_context)
	return globals()['sqlContextSingletonInstance']   

def send_df_to_dashboard(df):
	# extract the hashtags from dataframe and convert them into array
	top_tags = [str(t.hashtag) for t in df.select("hashtag").collect()]
	# extract the counts from dataframe and convert them into array
	tags_count = [p.hashtag_count for p in df.select("hashtag_count").collect()]
	# initialize and send the data through REST API
	url = 'http://server:5001/updateData'
	# url = 'http://localhost:5001/updateData'
	request_data = {'label': str(top_tags), 'data': str(tags_count)}
	response = requests.post(url, data=request_data)


if __name__ == "__main__": 
	main()	