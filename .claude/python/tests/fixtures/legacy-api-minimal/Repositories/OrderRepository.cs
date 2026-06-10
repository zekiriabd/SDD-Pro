using System.Collections.Generic;
using System.Data.SqlClient;
using LegacyApi.Models;

namespace LegacyApi.Repositories
{
    public class OrderRepository
    {
        private readonly string _conn;

        public OrderRepository(string conn)
        {
            _conn = conn;
        }

        public IEnumerable<OrderDto> FindActive()
        {
            using (var c = new SqlConnection(_conn))
            using (var cmd = new SqlCommand("SELECT Id, Total FROM Orders WHERE IsActive = 1", c))
            {
                c.Open();
                var list = new List<OrderDto>();
                using (var r = cmd.ExecuteReader())
                {
                    while (r.Read())
                    {
                        list.Add(new OrderDto { Id = (int)r["Id"], Total = (decimal)r["Total"] });
                    }
                }
                return list;
            }
        }

        public int Insert(OrderDto dto)
        {
            using (var c = new SqlConnection(_conn))
            using (var cmd = new SqlCommand("INSERT INTO Orders (Total) VALUES (@total); SELECT SCOPE_IDENTITY();", c))
            {
                cmd.Parameters.AddWithValue("@total", dto.Total);
                c.Open();
                return System.Convert.ToInt32(cmd.ExecuteScalar());
            }
        }
    }
}
